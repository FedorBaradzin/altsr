"""Доменные типы Risk Engine. Неизменяемые value-объекты, без сети и БД.

Денежные величины здесь — USD-оценка в float ТОЛЬКО для риск-решений (пороги/лимиты).
Фактический учёт средств ведётся в целочисленных минимальных единицах токена в ledger
(ТЗ §9); сюда приходит уже рассчитанная оценка.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

RiskVerdict = Literal["ALLOW", "BLOCK"]
Side = Literal["BUY", "SELL"]
SafetyVerdict = Literal["PASS", "REVIEW", "BLOCK", "UNKNOWN"]


@dataclass(frozen=True)
class RiskReason:
    """Причина блокировки. Все причины в решении — блокирующие."""

    code: str
    message: str


@dataclass(frozen=True)
class Position:
    """Открытая позиция в оценке USD."""

    token_key: str
    notional_usd: float
    unrealized_pnl_usd: float = 0.0


@dataclass(frozen=True)
class PortfolioState:
    """Снимок состояния портфеля на момент решения.

    data_fresh=False означает потерю достоверных рыночных данных → fail-closed.
    realized_pnl_today_usd отрицателен при убытке.
    """

    equity_usd: float
    open_positions: tuple[Position, ...] = ()
    realized_pnl_today_usd: float = 0.0
    data_fresh: bool = True

    @property
    def gross_exposure_usd(self) -> float:
        return sum(p.notional_usd for p in self.open_positions)

    @property
    def open_count(self) -> int:
        return len(self.open_positions)


@dataclass(frozen=True)
class TradeIntent:
    """Намерение совершить сделку. Приходит от Strategy/Execution, оценивается гейтом.

    is_exit=True — закрытие существующей позиции по безопасному пути (не новый вход).
    Поля котировки (quote_age_seconds, expected_slippage_pct, liquidity_usd) для входа
    обязательны: None трактуется как «нет данных» → отказ (fail-closed).
    """

    side: Side
    token_key: str
    chain: str
    token_address: str
    notional_usd: float
    recipient: str
    safety_verdict: SafetyVerdict | None = None
    quote_age_seconds: float | None = None
    expected_slippage_pct: float | None = None
    liquidity_usd: float | None = None
    strategy: str | None = None
    is_exit: bool = False

    @property
    def is_entry(self) -> bool:
        """Новый вход = покупка, не являющаяся закрытием позиции."""
        return self.side == "BUY" and not self.is_exit


@dataclass(frozen=True)
class RiskDecision:
    """Детерминированный вердикт гейта. Воспроизводим при тех же входах."""

    verdict: RiskVerdict
    reasons: tuple[RiskReason, ...]
    policy_version: str
    intent_key: str
    evaluated_at: datetime

    @property
    def allowed(self) -> bool:
        return self.verdict == "ALLOW"

    @property
    def blocked(self) -> bool:
        return self.verdict == "BLOCK"
