"""Portfolio-мультиплексор (T9): 1/N банка, агрегат, общий kill-switch."""
from __future__ import annotations

import pytest

from app.risk.portfolio import (
    Instance,
    MultiplexerConfig,
    aggregate,
    can_instance_enter,
    global_kill,
    per_instance_bank,
)


def _cfg(**over) -> MultiplexerConfig:
    base = dict(total_bank_usd=100_000.0, n_instances=4, global_stop_pct=0.20)
    base.update(over)
    return MultiplexerConfig(**base)


def test_per_instance_bank_is_one_over_n():
    assert per_instance_bank(_cfg()) == 25_000.0


def test_aggregate_is_sum_of_instances():
    insts = [Instance("a", 10_000, 500), Instance("b", 5_000, -200),
             Instance("c", 0, 0), Instance("d", 2_000, 100)]
    agg = aggregate(insts, _cfg())
    assert agg.total_deployed_usd == 17_000.0
    assert agg.total_realized_pnl_usd == 400.0


def test_total_exposure_never_exceeds_bank():
    # Сумма кэпов инстансов = банк: 4 * 25k = 100k.
    cfg = _cfg()
    assert per_instance_bank(cfg) * cfg.n_instances == cfg.total_bank_usd


def test_global_kill_trips_on_aggregate_drawdown():
    # Совокупный убыток −25% от банка > global_stop 20%.
    insts = [Instance("a", 0, -15_000), Instance("b", 0, -10_000)]
    assert global_kill(insts, _cfg()) is True


def test_global_kill_halts_all_instances():
    insts = [Instance("a", 0, -25_000)]
    killed = global_kill(insts, _cfg())
    for key in ("a", "b", "c", "d"):
        ok, reason = can_instance_enter(Instance(key), _cfg(),
                                        new_notional_usd=100.0, global_killed=killed)
        assert not ok and "kill-switch" in reason


def test_small_aggregate_loss_does_not_trip():
    insts = [Instance("a", 0, -5_000)]   # −5% < 20%
    assert global_kill(insts, _cfg()) is False


def test_instance_cannot_exceed_its_share():
    inst = Instance("a", deployed_usd=24_800.0)
    ok, reason = can_instance_enter(inst, _cfg(), new_notional_usd=500.0,
                                    global_killed=False)
    assert not ok and "доля инстанса" in reason
    # В пределах доли — можно.
    ok2, _ = can_instance_enter(Instance("a", 10_000.0), _cfg(),
                                new_notional_usd=500.0, global_killed=False)
    assert ok2


def test_config_validation():
    with pytest.raises(ValueError):
        MultiplexerConfig(total_bank_usd=100.0, n_instances=0)
