"""Реестр стратегий с версионированием (ТЗ §5)."""
from __future__ import annotations

import pytest

from app.strategy.lifecycle import IllegalTransition
from app.strategy.registry import StrategyRegistry
from app.strategy.types import ExitPlan, StrategyVersion


def _v1(**over) -> StrategyVersion:
    base = dict(
        version=1,
        notional_usd=100.0,
        exit_plan=ExitPlan(stop_loss_pct=0.25, take_profit_pct=(1.0,),
                           trailing_stop_pct=0.08, max_hold_minutes=240),
        min_confidence=0.5,
        risk_policy_version="risk-v1",
    )
    base.update(over)
    return StrategyVersion(**base)


def test_register_starts_candidate_at_version_1():
    reg = StrategyRegistry()
    d = reg.register("momentum", "Моментум-вход", _v1())
    assert d.key == "momentum"
    assert d.state == "CANDIDATE"
    assert d.current_version.version == 1
    assert d.can_trade  # CANDIDATE торгует (paper)


def test_register_rejects_duplicate_and_bad_first_version():
    reg = StrategyRegistry()
    reg.register("m", "M", _v1())
    with pytest.raises(ValueError):
        reg.register("m", "M2", _v1())
    reg2 = StrategyRegistry()
    with pytest.raises(ValueError):
        reg2.register("m", "M", _v1(version=2))


def test_add_version_increments_and_keeps_history():
    reg = StrategyRegistry()
    reg.register("m", "M", _v1())
    v2 = reg.add_version("m", notional_usd=250.0)
    assert v2.version == 2
    assert v2.notional_usd == 250.0
    # унаследовано из v1
    assert v2.min_confidence == 0.5
    assert reg.get("m").current_version.version == 2
    assert tuple(v.version for v in reg.versions("m")) == (1, 2)


def test_transition_updates_state():
    reg = StrategyRegistry()
    reg.register("m", "M", _v1())
    assert reg.transition("m", "approve").state == "ACTIVE"
    assert reg.transition("m", "pause").state == "PAUSED"
    with pytest.raises(IllegalTransition):
        reg.transition("m", "approve")
    assert reg.transition("m", "resume").state == "ACTIVE"
    assert reg.transition("m", "close").state == "CLOSED"
    assert not reg.get("m").can_trade  # CLOSED не торгует


def test_missing_strategy_raises():
    reg = StrategyRegistry()
    with pytest.raises(KeyError):
        reg.get("nope")
    assert reg.list_keys() == ()
