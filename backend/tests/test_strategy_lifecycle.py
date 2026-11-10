"""Жизненный цикл стратегии — конечный автомат (ТЗ §5).

Контракт переходов: только разрешённые ребра; CLOSED терминально.
"""
from __future__ import annotations

import pytest

from app.strategy.lifecycle import (
    IllegalTransition,
    can_transition,
    is_terminal,
    next_state,
)


@pytest.mark.parametrize(
    "state,event,expected",
    [
        ("CANDIDATE", "approve", "ACTIVE"),
        ("CANDIDATE", "reject", "CLOSED"),
        ("CANDIDATE", "close", "CLOSED"),
        ("ACTIVE", "pause", "PAUSED"),
        ("ACTIVE", "close", "CLOSED"),
        ("PAUSED", "resume", "ACTIVE"),
        ("PAUSED", "close", "CLOSED"),
    ],
)
def test_allowed_transitions(state, event, expected):
    assert next_state(state, event) == expected
    assert can_transition(state, event)


@pytest.mark.parametrize(
    "state,event",
    [
        ("CANDIDATE", "pause"),    # нельзя паузить кандидата
        ("CANDIDATE", "resume"),
        ("ACTIVE", "approve"),     # уже активна
        ("ACTIVE", "resume"),
        ("PAUSED", "pause"),
        ("CLOSED", "approve"),     # терминальное
        ("CLOSED", "resume"),
        ("CLOSED", "close"),
    ],
)
def test_illegal_transitions_raise(state, event):
    assert not can_transition(state, event)
    with pytest.raises(IllegalTransition):
        next_state(state, event)


def test_closed_is_terminal():
    assert is_terminal("CLOSED")
    for s in ("CANDIDATE", "ACTIVE", "PAUSED"):
        assert not is_terminal(s)


def test_full_lifecycle_path():
    s = "CANDIDATE"
    s = next_state(s, "approve")   # ACTIVE
    s = next_state(s, "pause")     # PAUSED
    s = next_state(s, "resume")    # ACTIVE
    s = next_state(s, "close")     # CLOSED
    assert s == "CLOSED"
    assert is_terminal(s)
