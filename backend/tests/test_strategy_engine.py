"""Движок решений стратегии (ТЗ §5).

Каждое решение несёт снимок рынка, основание входа, план выхода и результат Risk
Engine. ENTER только при ALLOW; BLOCK → REJECTED (но решение сохраняется для аудита).
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.risk.policy import RiskPolicy
from app.risk.types import PortfolioState
from app.strategy.engine import decide
from app.strategy.registry import StrategyRegistry
from app.strategy.types import EntryRationale, ExitPlan, MarketSnapshot, StrategyVersion

NOW = datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc)
RECIPIENT = "0xportfolio"


def _policy(**over) -> RiskPolicy:
    base = dict(
        version="risk-v1",
        max_position_pct=0.01,
        max_exposure_pct=0.20,
        daily_loss_limit_pct=0.02,
        max_open_positions=5,
        max_slippage_pct=0.01,
        min_liquidity_usd=10_000.0,
        max_quote_age_seconds=30.0,
        allowed_safety_verdicts=("PASS",),
        block_on_stale_data=True,
    )
    base.update(over)
    return RiskPolicy(**base)


def _portfolio(**over) -> PortfolioState:
    base = dict(equity_usd=100_000.0, open_positions=(),
                realized_pnl_today_usd=0.0, data_fresh=True)
    base.update(over)
    return PortfolioState(**base)


def _version(**over) -> StrategyVersion:
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


def _active(reg: StrategyRegistry | None = None, **vover):
    reg = reg or StrategyRegistry()
    reg.register("momentum", "Моментум", _version(**vover))
    reg.transition("momentum", "approve")
    return reg.get("momentum")


def _snapshot(**over) -> MarketSnapshot:
    base = dict(token_key="sol:MINT", chain="solana", token_address="MINT",
                price_usd=1.0, liquidity_usd=50_000.0, volume_h1_usd=120_000.0,
                price_change_m5=3.0, buys_m5=20, sells_m5=8,
                captured_at=NOW, data_fresh=True)
    base.update(over)
    return MarketSnapshot(**base)


def _rationale(**over) -> EntryRationale:
    base = dict(reasons=("моментум m5 +3%", "buys/sells 2.5"),
                confidence=0.8, signal_source="momentum-v1")
    base.update(over)
    return EntryRationale(**base)


def test_enter_when_active_and_risk_allows():
    d = decide(_active(), _snapshot(), _rationale(), _policy(), _portfolio(),
               recipient=RECIPIENT, safety_verdict="PASS",
               quote_age_seconds=5.0, expected_slippage_pct=0.005, now=NOW)
    assert d.action == "ENTER"
    assert d.entered
    # Запись несёт всё необходимое для аудита.
    assert d.risk_decision is not None and d.risk_decision.allowed
    assert d.exit_plan is not None and d.exit_plan.stop_loss_pct == 0.25
    assert d.intent is not None and d.intent.notional_usd == 100.0
    assert d.snapshot.token_key == "sol:MINT"
    assert "моментум m5 +3%" in d.reasons


def test_skip_when_not_trading_state():
    reg = StrategyRegistry()
    reg.register("m", "M", _version())
    reg.transition("m", "approve")
    reg.transition("m", "pause")       # PAUSED — не торгует
    d = decide(reg.get("m"), _snapshot(), _rationale(), _policy(), _portfolio(),
               recipient=RECIPIENT, safety_verdict="PASS",
               quote_age_seconds=5.0, expected_slippage_pct=0.005, now=NOW)
    assert d.action == "SKIP"
    assert d.intent is None and d.risk_decision is None
    assert "PAUSED" in d.skip_reason


def test_skip_when_confidence_below_threshold():
    d = decide(_active(), _snapshot(), _rationale(confidence=0.3),
               _policy(), _portfolio(), recipient=RECIPIENT,
               safety_verdict="PASS", quote_age_seconds=5.0,
               expected_slippage_pct=0.005, now=NOW)
    assert d.action == "SKIP"
    assert "уверенность" in d.skip_reason


def test_rejected_when_safety_not_pass():
    d = decide(_active(), _snapshot(), _rationale(), _policy(), _portfolio(),
               recipient=RECIPIENT, safety_verdict="REVIEW",
               quote_age_seconds=5.0, expected_slippage_pct=0.005, now=NOW)
    assert d.action == "REJECTED"
    assert d.rejected
    assert d.risk_decision is not None and d.risk_decision.blocked
    # Причина риска подмешана в reasons решения.
    assert len(d.reasons) > len(d.rationale.reasons)


def test_rejected_on_stale_snapshot_fail_closed():
    d = decide(_active(), _snapshot(data_fresh=False), _rationale(),
               _policy(), _portfolio(), recipient=RECIPIENT,
               safety_verdict="PASS", quote_age_seconds=5.0,
               expected_slippage_pct=0.005, now=NOW)
    assert d.action == "REJECTED"
    assert any("market_data_stale" == r.code for r in d.risk_decision.reasons)


def test_rejected_when_position_too_large():
    d = decide(_active(notional_usd=5_000.0), _snapshot(), _rationale(),
               _policy(), _portfolio(), recipient=RECIPIENT,
               safety_verdict="PASS", quote_age_seconds=5.0,
               expected_slippage_pct=0.005, now=NOW)
    # 5000 > 1% от 100k = 1000 → BLOCK
    assert d.action == "REJECTED"


def test_decision_is_deterministic():
    args = dict(recipient=RECIPIENT, safety_verdict="PASS",
                quote_age_seconds=5.0, expected_slippage_pct=0.005, now=NOW)
    d1 = decide(_active(), _snapshot(), _rationale(), _policy(), _portfolio(), **args)
    d2 = decide(_active(), _snapshot(), _rationale(), _policy(), _portfolio(), **args)
    assert d1 == d2
