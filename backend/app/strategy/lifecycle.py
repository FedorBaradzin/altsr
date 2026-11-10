"""Жизненный цикл стратегии (ТЗ §5): детерминированный конечный автомат.

Разрешённые переходы:
    CANDIDATE --approve--> ACTIVE
    CANDIDATE --reject---> CLOSED
    ACTIVE    --pause----> PAUSED
    PAUSED    --resume---> ACTIVE
    ACTIVE    --close----> CLOSED
    PAUSED    --close----> CLOSED
CLOSED — терминальное состояние, выходов нет. Любой иной переход → IllegalTransition.
"""
from __future__ import annotations

from typing import Literal

from .types import StrategyState

StrategyEvent = Literal["approve", "reject", "pause", "resume", "close"]

# (состояние, событие) -> новое состояние.
_TRANSITIONS: dict[tuple[StrategyState, StrategyEvent], StrategyState] = {
    ("CANDIDATE", "approve"): "ACTIVE",
    ("CANDIDATE", "reject"): "CLOSED",
    ("CANDIDATE", "close"): "CLOSED",
    ("ACTIVE", "pause"): "PAUSED",
    ("ACTIVE", "close"): "CLOSED",
    ("PAUSED", "resume"): "ACTIVE",
    ("PAUSED", "close"): "CLOSED",
}

TERMINAL_STATES: frozenset[StrategyState] = frozenset({"CLOSED"})


class IllegalTransition(ValueError):
    """Недопустимый переход состояния стратегии."""

    def __init__(self, state: StrategyState, event: StrategyEvent) -> None:
        self.state = state
        self.event = event
        super().__init__(f"Переход {state} --{event}--> недопустим")


def next_state(state: StrategyState, event: StrategyEvent) -> StrategyState:
    """Возвращает новое состояние или бросает IllegalTransition."""
    try:
        return _TRANSITIONS[(state, event)]
    except KeyError:
        raise IllegalTransition(state, event) from None


def can_transition(state: StrategyState, event: StrategyEvent) -> bool:
    """True, если переход разрешён (без побочных эффектов)."""
    return (state, event) in _TRANSITIONS


def is_terminal(state: StrategyState) -> bool:
    return state in TERMINAL_STATES
