"""Аварийная остановка (kill switch) — ТЗ §6, критерий приёмки AC-15.

При аварии новые входы блокируются. Закрытие существующих позиций допускается
только по безопасному пути и только при наличии достоверных котировок.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.risk.engine import evaluate
from app.risk.killswitch import TRIP_REASONS, KillSwitchState, clear, trip
from app.risk.policy import RiskPolicy
from app.risk.types import PortfolioState, TradeIntent

NOW = datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc)


def _policy() -> RiskPolicy:
    return RiskPolicy(
        version="test-v1", max_position_pct=0.01, max_exposure_pct=0.20,
        daily_loss_limit_pct=0.02, max_open_positions=5, max_slippage_pct=0.01,
        min_liquidity_usd=10_000.0, max_quote_age_seconds=30.0,
    )


def _buy(**over) -> TradeIntent:
    base = dict(
        side="BUY", token_key="eth:0xabc", chain="eth", token_address="0xabc",
        notional_usd=500.0, recipient="0xOWNER", safety_verdict="PASS",
        quote_age_seconds=5.0, expected_slippage_pct=0.004, liquidity_usd=50_000.0,
        strategy="early_discovery", is_exit=False,
    )
    base.update(over)
    return TradeIntent(**base)


def test_trip_sets_active_with_reason_and_time():
    ks = trip("limit_breach", now=NOW)
    assert ks.active
    assert ks.reason == "limit_breach"
    assert ks.tripped_at == NOW


def test_clear_deactivates():
    ks = clear()
    assert not ks.active
    assert ks.reason is None


def test_known_trip_reasons_are_enumerated():
    # ТЗ §6 перечисляет условия аварийной остановки — они должны иметь коды.
    for code in ("market_data_lost", "balance_mismatch", "key_compromise",
                 "limit_breach", "ambiguous_tx", "contract_change",
                 "mass_execution_errors", "user_revoked", "admin_manual"):
        assert code in TRIP_REASONS


def test_killswitch_blocks_new_buy():
    ks = trip("admin_manual", now=NOW)
    d = evaluate(_buy(), _policy(), PortfolioState(equity_usd=100_000.0),
                 killswitch=ks, now=NOW)
    assert d.blocked
    assert any(r.code == "emergency_stop" for r in d.reasons)


def test_killswitch_allows_exit_sell_with_fresh_data():
    ks = trip("admin_manual", now=NOW)
    intent = _buy(side="SELL", is_exit=True)
    d = evaluate(intent, _policy(), PortfolioState(equity_usd=100_000.0, data_fresh=True),
                 killswitch=ks, now=NOW)
    assert d.allowed, d.reasons


def test_killswitch_blocks_exit_sell_when_data_stale():
    ks = trip("market_data_lost", now=NOW)
    intent = _buy(side="SELL", is_exit=True)
    d = evaluate(intent, _policy(), PortfolioState(equity_usd=100_000.0, data_fresh=False),
                 killswitch=ks, now=NOW)
    assert d.blocked
    assert any(r.code == "market_data_stale" for r in d.reasons)


def test_inactive_killswitch_does_not_block():
    d = evaluate(_buy(), _policy(), PortfolioState(equity_usd=100_000.0),
                 killswitch=KillSwitchState(active=False), now=NOW)
    assert d.allowed, d.reasons
