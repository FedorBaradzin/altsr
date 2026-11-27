"""Эвристика smart-money v1 — ЧЕСТНОЕ определение «notable»-кошелька.

Чистая детерминированная логика (без сети и БД), покрываемая unit-тестами.

ЧТО ЭТО:
  «notable»-кошелёк = РАННИЙ ПОВТОРЯЮЩИЙСЯ ПОКУПАТЕЛЬ. Кошелёк считается
  ранним покупателем токена, если он попадает в первые N buy-сделок пула
  (по доступной истории сделок). Кошелёк становится «notable», когда он —
  ранний покупатель у >= K РАЗНЫХ токенов с вердиктом PASS (анти-скам).

ЧЕМ ЭТО НЕ ЯВЛЯЕТСЯ (важно, не вводим в заблуждение):
  Это НЕ сертифицированное отслеживание прибыльных кошельков. Мы НЕ считаем
  PnL и НЕ знаем, заработал ли кошелёк. «Ранний покупатель PASS-токенов» —
  всего лишь поведенческий прокси внимания/опыта, который может коррелировать
  (а может и нет) с качеством. Для будущей разметки по реальной прибыли
  зарезервировано поле SmartWallet.label (NULL = не размечен).

ОГРАНИЧЕНИЕ ДАННЫХ:
  Бесключевой trades-эндпоинт отдаёт лишь последние ~300 сделок за ~24ч, то
  есть «первые N buy» — это первые покупки В ПРЕДЕЛАХ доступного окна. Для
  новых пулов (цель раннего радара) окно обычно покрывает всю их жизнь, и
  метрика осмысленна; для старых пулов это лишь «ранние среди недавних».
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .gecko_trades import Trade


def norm_wallet(addr: str) -> str:
    """Нормализация адреса кошелька под стабильный ключ (как в discovery.base).

    EVM (0x…) — hex, регистронезависим → в нижний регистр. Solana base58
    РЕГИСТРОЗАВИСИМ → сохраняем оригинальный регистр.
    """
    a = (addr or "").strip()
    if not a:
        return ""
    return a.lower() if a[:2].lower() == "0x" else a


@dataclass(slots=True)
class EarlyBuyer:
    """Ранний покупатель токена (одна запись на кошелёк, по первой его покупке)."""

    wallet: str
    rank: int                 # 0-based позиция среди ранних buy-сделок
    ts: datetime | None       # время первой покупки кошелька
    volume_usd: float | None


def _ts_key(t: Trade) -> float:
    """Ключ сортировки по времени (сделки без ts уводим в конец)."""
    return t.ts.timestamp() if t.ts is not None else float("inf")


def extract_early_buyers(trades: list[Trade], early_n: int) -> list[EarlyBuyer]:
    """Выделить первых early_n РАЗНЫХ кошельков-покупателей (по времени, по возр.).

    Берём только buy-сделки, сортируем по времени (старые сначала), дедуплицируем
    кошельки (оставляя самую раннюю покупку), возвращаем первые early_n.
    Пустой вход / early_n<=0 → []. Ничего не выдумываем.
    """
    if early_n <= 0:
        return []
    buys = sorted((t for t in trades if t.is_buy), key=_ts_key)
    out: list[EarlyBuyer] = []
    seen: set[str] = set()
    for t in buys:
        w = norm_wallet(t.wallet)
        if not w or w in seen:
            continue
        seen.add(w)
        out.append(EarlyBuyer(wallet=w, rank=len(out), ts=t.ts, volume_usd=t.volume_usd))
        if len(out) >= early_n:
            break
    return out


def is_notable(early_pass_count: int, min_pass_for_notable: int) -> bool:
    """Notable, если кошелёк — ранний покупатель у >= K разных PASS-токенов."""
    return early_pass_count >= max(1, min_pass_for_notable)
