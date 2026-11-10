"""Доменные типы Strategy Engine. Неизменяемые value-объекты, без сети и БД.

Денежные величины — USD-оценка в float ТОЛЬКО для решений (как в Risk Engine).
Фактический учёт ведётся в целочисленных минимальных единицах в ledger (ТЗ §9).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from ..risk.types import RiskDecision, TradeIntent

# Жизненный цикл стратегии (ТЗ §5).
# CANDIDATE — предложена, оценивается (только бумажный/теневой режим).
# ACTIVE    — одобрена, формирует входы.
# PAUSED    — временно остановлена (оператор/kill-switch), можно возобновить.
# CLOSED    — завершена; терминальное состояние, выходов из него нет.
StrategyState = Literal["CANDIDATE", "ACTIVE", "PAUSED", "CLOSED"]

# Итог решения движка по одному кандидату.
# ENTER    — вход сформирован и пропущен Risk Engine.
# REJECTED — вход сформирован, но заблокирован Risk Engine (запись для аудита).
# SKIP     — стратегия не торгует в текущем состоянии / нет основания входа.
StrategyAction = Literal["ENTER", "REJECTED", "SKIP"]

_TRADING_STATES: frozenset[str] = frozenset({"CANDIDATE", "ACTIVE"})


@dataclass(frozen=True)
class MarketSnapshot:
    """Снимок рынка на момент решения. Записывается с каждым решением (ТЗ §5).

    data_fresh=False — данные устарели/потеряны → вход должен быть запрещён
    (fail-closed проверяет Risk Engine по portfolio.data_fresh).
    """

    token_key: str
    chain: str
    token_address: str
    price_usd: float | None = None
    liquidity_usd: float | None = None
    volume_h1_usd: float | None = None
    price_change_m5: float | None = None
    price_change_h1: float | None = None
    buys_m5: int | None = None
    sells_m5: int | None = None
    captured_at: datetime | None = None
    data_fresh: bool = True


@dataclass(frozen=True)
class EntryRationale:
    """Почему стратегия хочет войти. Основание входа (ТЗ §5)."""

    reasons: tuple[str, ...] = ()
    confidence: float = 0.0
    signal_source: str | None = None


@dataclass(frozen=True)
class ExitPlan:
    """Детерминированный план выхода, фиксируемый на входе (ТЗ §5).

    take_profit_pct — уровни частичной фиксации (доли прибыли, по возрастанию);
    stop_loss_pct — стоп от цены входа (положительное число = просадка);
    trailing_stop_pct — трейлинг от пика (None = выключен);
    max_hold_minutes — предельное время удержания (None = без лимита).
    """

    stop_loss_pct: float
    take_profit_pct: tuple[float, ...] = ()
    trailing_stop_pct: float | None = None
    max_hold_minutes: int | None = None
    basis: str | None = None

    def __post_init__(self) -> None:
        if self.stop_loss_pct <= 0:
            raise ValueError("stop_loss_pct должен быть > 0")
        if self.trailing_stop_pct is not None and self.trailing_stop_pct <= 0:
            raise ValueError("trailing_stop_pct должен быть > 0 или None")
        if any(tp <= 0 for tp in self.take_profit_pct):
            raise ValueError("уровни take_profit_pct должны быть > 0")
        if list(self.take_profit_pct) != sorted(self.take_profit_pct):
            raise ValueError("take_profit_pct должны идти по возрастанию")


@dataclass(frozen=True)
class StrategyVersion:
    """Неизменяемая версия конфигурации стратегии. Реестр хранит историю версий.

    min_confidence — порог уверенности сигнала для входа;
    notional_usd — размер ставки (оценка USD) нового входа;
    exit_plan — шаблон плана выхода;
    risk_policy_version — ссылка на версию риск-политики (двойной контроль).
    """

    version: int
    notional_usd: float
    exit_plan: ExitPlan
    min_confidence: float = 0.0
    risk_policy_version: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("version нумеруется с 1")
        if self.notional_usd <= 0:
            raise ValueError("notional_usd должен быть > 0")
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("min_confidence в диапазоне [0, 1]")


@dataclass(frozen=True)
class StrategyDefinition:
    """Снимок стратегии из реестра: ключ, состояние и текущая версия."""

    key: str
    name: str
    state: StrategyState
    current_version: StrategyVersion

    @property
    def can_trade(self) -> bool:
        """Формирует ли входы в текущем состоянии (CANDIDATE/ACTIVE)."""
        return self.state in _TRADING_STATES


@dataclass(frozen=True)
class StrategyDecision:
    """Запись решения. Воспроизводима при тех же входах.

    Несёт всё для аудита (ТЗ §5): снимок рынка, основание входа, план выхода и
    результат Risk Engine. intent/risk_decision = None, когда action=SKIP.
    """

    strategy_key: str
    version: int
    state: StrategyState
    action: StrategyAction
    snapshot: MarketSnapshot
    rationale: EntryRationale
    decided_at: datetime
    intent: TradeIntent | None = None
    exit_plan: ExitPlan | None = None
    risk_decision: RiskDecision | None = None
    skip_reason: str | None = None
    reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def entered(self) -> bool:
        return self.action == "ENTER"

    @property
    def rejected(self) -> bool:
        return self.action == "REJECTED"

    @property
    def skipped(self) -> bool:
        return self.action == "SKIP"
