"""Шина доменных событий ALTSR → Redis pub/sub (бэкенд только эмитит, фронта нет).

Назначение
----------
Единая точка, где бизнес-логика публикует доменные события, а подписчики
(дашборд, боты, будущий WebSocket-мост) читают их из Redis pub/sub. Здесь — только
схема событий и эмиссия; потребителей (фронт) в этом модуле нет.

Каналы Redis pub/sub
--------------------
Все каналы с префиксом ``altsr:events:``:

- ``altsr:events:equity_tick`` — срез equity/баланса бумажного счёта.
- ``altsr:events:stage`` — смена фазы прохождения токена по воронке
  (discovered → screened → signalled → entered → exited).
- ``altsr:events:trade`` — факт сделки (открытие/частичное/закрытие позиции).
- ``altsr:events:rule_fired`` — сработало правило риск-движка (стоп, трейлинг,
  take-profit, kill switch и т.п.).
- ``altsr:events:signal`` — сгенерирован торговый сигнал (BUY).

Схема payload
-------------
Каждое событие сериализуется в JSON с общими полями:

- ``type`` — тип события (``equity_tick`` | ``stage`` | ``trade`` | ``rule_fired``
  | ``signal``);
- ``ts`` — время события (ISO-8601, UTC);
- ``id`` — идентичность события для дедупа (см. ``Event.identity``);

плюс полезная нагрузка, специфичная для типа (см. датаклассы ниже).

Дедуп
-----
``publish`` перед отправкой ставит короткоживущий Redis-ключ
``altsr:event:{identity}`` через ``SET NX EX`` — зеркалит подход
``altsr:alert:{code}`` из :mod:`app.notify.alerts`. Если ключ уже есть — событие
не публикуется повторно. Без Redis дедупа нет (публикуем всегда).

Тихие часы и дайджест
---------------------
В тихие часы (``QUIET_HOURS_START``..``QUIET_HOURS_END``) пер-событийные
Telegram-уведомления не шлём, а копим события в окно и в ``DIGEST_AT`` собираем
единый дайджест. Сборка дайджеста — чистая функция :func:`build_digest`,
детектор тихих часов — :func:`in_quiet_hours`; обе тестируемы без Redis/сети.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger("altsr.notify.events")

# Префикс всех каналов шины и префикс ключа дедупа.
CHANNEL_PREFIX = "altsr:events:"
DEDUP_KEY_PREFIX = "altsr:event:"

# Тип события → имя канала (без общего префикса).
_CHANNEL_BY_TYPE = {
    "equity_tick": "equity_tick",
    "stage": "stage",
    "trade": "trade",
    "rule_fired": "rule_fired",
    "signal": "signal",
}

# Фазы прохождения токена по воронке (для stage_event).
STAGES = ("discovered", "screened", "signalled", "entered", "exited")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class Event:
    """Базовое доменное событие.

    Поля ``type``/``ts`` общие для всех; ``identity`` задаёт ключ дедупа —
    два события с одинаковой идентичностью считаются одним и тем же.
    """

    type: str
    ts: str = field(default_factory=_utcnow_iso)

    @property
    def channel(self) -> str:
        """Полное имя Redis-канала для этого события."""
        return CHANNEL_PREFIX + _CHANNEL_BY_TYPE[self.type]

    @property
    def identity(self) -> str:
        """Ключ дедупа. По умолчанию — тип (переопределяется в наследниках)."""
        return self.type

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


@dataclass(slots=True)
class EquityTick(Event):
    """Срез equity/баланса бумажного счёта.

    Канал: ``altsr:events:equity_tick``.
    Идентичность: тип + минута среза (чтобы не плодить дубли внутри минуты).
    """

    equity_usd: float = 0.0
    balance_usd: float = 0.0
    open_positions: int = 0
    realized_pnl_usd: float = 0.0
    type: str = field(default="equity_tick", init=False)

    @property
    def identity(self) -> str:
        return f"equity_tick:{self.ts[:16]}"  # до минут: YYYY-MM-DDTHH:MM


@dataclass(slots=True)
class StageEvent(Event):
    """Переход токена между фазами воронки.

    Канал: ``altsr:events:stage``.
    Идентичность: тип + chain + address + stage (один переход — одно событие).
    """

    chain: str = ""
    address: str = ""
    symbol: str | None = None
    stage: str = ""
    type: str = field(default="stage", init=False)

    @property
    def identity(self) -> str:
        return f"stage:{self.chain}:{self.address}:{self.stage}"


@dataclass(slots=True)
class TradeEvent(Event):
    """Факт сделки по бумажной позиции (открытие/частичное/закрытие).

    Канал: ``altsr:events:trade``.
    Идентичность: тип + id сделки (или chain:address:action, если id нет).
    """

    chain: str = ""
    address: str = ""
    symbol: str | None = None
    action: str = ""  # open | take_profit | close | partial
    size_usd: float = 0.0
    price: float | None = None
    pnl_usd: float | None = None
    trade_id: str | None = None
    type: str = field(default="trade", init=False)

    @property
    def identity(self) -> str:
        if self.trade_id:
            return f"trade:{self.trade_id}"
        return f"trade:{self.chain}:{self.address}:{self.action}:{self.ts}"


@dataclass(slots=True)
class RuleFired(Event):
    """Сработало правило риск-движка (стоп/трейлинг/тейк/kill switch).

    Канал: ``altsr:events:rule_fired``.
    Идентичность: тип + rule + chain:address (одно срабатывание правила на позицию).
    """

    rule: str = ""
    chain: str = ""
    address: str = ""
    symbol: str | None = None
    detail: str = ""
    type: str = field(default="rule_fired", init=False)

    @property
    def identity(self) -> str:
        return f"rule_fired:{self.rule}:{self.chain}:{self.address}"


@dataclass(slots=True)
class SignalEvent(Event):
    """Сгенерирован торговый сигнал (BUY).

    Канал: ``altsr:events:signal``.
    Идентичность: тип + chain:address (один сигнал на токен).
    """

    chain: str = ""
    address: str = ""
    symbol: str | None = None
    confidence: float = 0.0
    risk_score: int | None = None
    type: str = field(default="signal", init=False)

    @property
    def identity(self) -> str:
        return f"signal:{self.chain}:{self.address}"


async def _should_publish(redis, identity: str, dedup_seconds: int) -> bool:
    """True, если событие с этой идентичностью ещё не публиковалось в окне дедупа.

    Зеркалит дедуп из :mod:`app.notify.alerts`: ``SET NX EX`` на ключ
    ``altsr:event:{identity}``. Без Redis или при ``dedup_seconds <= 0`` — всегда True.
    """
    if redis is None or dedup_seconds <= 0:
        return True
    key = f"{DEDUP_KEY_PREFIX}{identity}"
    try:
        was_set = await redis.set(key, "1", nx=True, ex=dedup_seconds)
    except Exception as exc:  # noqa: BLE001 — дедуп не должен ронять эмиссию
        logger.warning("Дедуп события недоступен (%s) — публикуем без дедупа", exc)
        return True
    return bool(was_set)


async def publish(redis, event: Event, *, dedup_seconds: int = 300) -> bool:
    """Опубликовать событие в его Redis-канал ровно один раз (с дедупом).

    Возвращает True, если событие ушло в канал; False — если подавлено дедупом
    или Redis отсутствует.
    """
    if redis is None:
        logger.info("Redis недоступен — событие %s не опубликовано", event.type)
        return False
    if not await _should_publish(redis, event.identity, dedup_seconds):
        logger.info("Событие %s подавлено дедупом", event.identity)
        return False
    await redis.publish(event.channel, event.to_json())
    return True


def in_quiet_hours(hour: int, start: int, end: int) -> bool:
    """Попадает ли час ``hour`` [0..23] в окно тихих часов [start, end).

    Поддерживает окно через полночь (например, 23..8): если ``start > end``,
    тихое время — это ``hour >= start`` ИЛИ ``hour < end``. При ``start == end``
    тихих часов нет.
    """
    start %= 24
    end %= 24
    hour %= 24
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def build_digest(events: list[Event]) -> str:
    """Собрать текст дайджеста из накопленных за окно событий (чистая функция).

    Группирует события по типу и даёт компактную сводку. Пустой список →
    короткое сообщение «событий не было».
    """
    if not events:
        return "🌙 <b>ALTSR · дайджест</b>\nЗа тихие часы событий не было."

    by_type: dict[str, int] = {}
    for e in events:
        by_type[e.type] = by_type.get(e.type, 0) + 1

    trades = [e for e in events if isinstance(e, TradeEvent)]
    signals = [e for e in events if isinstance(e, SignalEvent)]
    rules = [e for e in events if isinstance(e, RuleFired)]
    realized = sum((t.pnl_usd or 0.0) for t in trades)

    lines = [
        "🌙 <b>ALTSR · дайджест за тихие часы</b>",
        f"Всего событий: {len(events)}",
    ]
    order = ("signal", "stage", "trade", "rule_fired", "equity_tick")
    parts = [f"{t}: {by_type[t]}" for t in order if t in by_type]
    if parts:
        lines.append("По типам — " + "; ".join(parts))
    if signals:
        lines.append(f"Сигналов (BUY): {len(signals)}")
    if trades:
        lines.append(f"Сделок: {len(trades)} · реализованный PnL: ${realized:,.2f}")
    if rules:
        fired = "; ".join(sorted({r.rule for r in rules if r.rule}))
        lines.append(f"Сработавшие правила: {fired}" if fired else f"Правил: {len(rules)}")
    return "\n".join(lines)


class DigestCollector:
    """Буфер событий для тихих часов.

    В тихие часы ``add`` копит события; ``flush`` отдаёт накопленное и очищает
    буфер — для сборки дайджеста в ``DIGEST_AT``. Состояние держится в памяти
    процесса; вся логика форматирования — в чистой :func:`build_digest`.
    """

    def __init__(self) -> None:
        self._buffer: list[Event] = []

    def add(self, event: Event) -> None:
        self._buffer.append(event)

    @property
    def pending(self) -> list[Event]:
        return list(self._buffer)

    def __len__(self) -> int:
        return len(self._buffer)

    def flush(self) -> list[Event]:
        """Вернуть накопленные события и очистить буфер."""
        events = self._buffer
        self._buffer = []
        return events

    def build_and_flush(self) -> str:
        """Собрать дайджест из буфера и очистить его."""
        return build_digest(self.flush())
