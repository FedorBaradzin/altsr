"""Session controller (T5): budget_cap, session-stop → kill-switch, fail-closed."""
from __future__ import annotations

from app.risk.session import SessionConfig, SessionSnapshot, evaluate_session


def _cfg(**over) -> SessionConfig:
    base = dict(budget_cap_usd=10_000.0, session_stop_pct=0.20)
    base.update(over)
    return SessionConfig(**base)


def _snap(**over) -> SessionSnapshot:
    base = dict(start_equity_usd=100_000.0, deployed_usd=0.0, realized_pnl_usd=0.0)
    base.update(over)
    return SessionSnapshot(**base)


def test_clean_session_allows_entry():
    d = evaluate_session(_snap(), _cfg(), new_notional_usd=500.0)
    assert d.can_enter and not d.trip_kill_switch


def test_budget_cap_blocks_entry_without_kill_switch():
    d = evaluate_session(_snap(deployed_usd=9_800.0), _cfg(), new_notional_usd=500.0)
    assert not d.can_enter and not d.trip_kill_switch
    assert any("budget cap" in r for r in d.reasons)


def test_session_stop_trips_kill_switch_and_blocks():
    # Реализованный убыток −25% > session_stop 20% → стоп + kill-switch.
    d = evaluate_session(_snap(realized_pnl_usd=-25_000.0), _cfg(), new_notional_usd=100.0)
    assert d.trip_kill_switch and not d.can_enter
    assert any("session-stop" in r for r in d.reasons)


def test_small_loss_does_not_trip():
    d = evaluate_session(_snap(realized_pnl_usd=-5_000.0), _cfg())  # −5% < 20%
    assert d.can_enter and not d.trip_kill_switch


def test_unknown_equity_fails_closed():
    d = evaluate_session(_snap(start_equity_usd=0.0), _cfg())
    assert not d.can_enter
    assert "equity" in d.reasons[0]


def test_disabled_caps_allow_everything():
    d = evaluate_session(
        _snap(deployed_usd=1_000_000.0, realized_pnl_usd=-90_000.0),
        _cfg(budget_cap_usd=0.0, session_stop_pct=0.0), new_notional_usd=50_000.0,
    )
    assert d.can_enter and not d.trip_kill_switch


def test_drawdown_pct_computation():
    assert _snap(realized_pnl_usd=-20_000.0).drawdown_pct == 0.20
    assert _snap(realized_pnl_usd=5_000.0).drawdown_pct == 0.0   # прибыль → 0
