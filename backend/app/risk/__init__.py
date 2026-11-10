"""Risk Engine (ТЗ §6) — детерминированный гейт допуска сделок.

Независим от AI, стратегии и маршрутизатора. AI формирует исследовательский сигнал,
но НЕ имеет права исполнять: решение о допуске принимает только этот движок.
"""
from __future__ import annotations

from .delegation import DelegationPolicy, SpendState
from .engine import evaluate
from .killswitch import TRIP_REASONS, KillSwitchState, clear, trip
from .policy import DEFAULT_POLICY, RiskPolicy
from .types import (
    PortfolioState,
    Position,
    RiskDecision,
    RiskReason,
    TradeIntent,
)

__all__ = [
    "evaluate",
    "RiskPolicy",
    "DEFAULT_POLICY",
    "KillSwitchState",
    "trip",
    "clear",
    "TRIP_REASONS",
    "DelegationPolicy",
    "SpendState",
    "TradeIntent",
    "PortfolioState",
    "Position",
    "RiskDecision",
    "RiskReason",
]
