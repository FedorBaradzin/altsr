"""Risk Engine — центральный детерминированный гейт (ТЗ §6).

Движок независим от AI, стратегии и маршрутизатора. Чистая логика, без сети/БД.
Принцип fail-closed: при отсутствии достоверных данных вход запрещён.

Эти тесты — контракт движка. Негативные сценарии покрывают критерии приёмки:
AC-07 (лимит расходов/размер позиции), AC-08 (отказ при неполных данных безопасности).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.risk.engine import evaluate
from app.risk.policy import RiskPolicy
from app.risk.types import PortfolioState, Position, TradeIntent

NOW = datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc)


def _policy(**over) -> RiskPolicy:
    base = dict(
        version="test-v1",
        max_position_pct=0.01,      # 1% equity
        max_exposure_pct=0.20,      # 20% equity
        daily_loss_limit_pct=0.02,  # 2% equity
        max_open_positions=5,
        max_slippage_pct=0.01,      # 1%
        min_liquidity_usd=10_000.0,
        max_quote_age_seconds=30.0,
        allowed_safety_verdicts=("PASS",),
        block_on_stale_data=True,
    )
    base.update(over)
    return RiskPolicy(**base)


def _portfolio(**over) -> PortfolioState:
    base = dict(
        equity_usd=100_000.0,
        open_positions=(),
        realized_pnl_today_usd=0.0,
        data_fresh=True,
    )
    base.update(over)
    return PortfolioState(**base)


def _buy(**over) -> TradeIntent:
    base = dict(
        side="BUY",
        token_key="eth:0xabc",
        chain="eth",
        token_address="0xabc",
        notional_usd=500.0,          # 0.5% of 100k equity → под лимитом 1%
        recipient="0xOWNER",
        safety_verdict="PASS",
        quote_age_seconds=5.0,
        expected_slippage_pct=0.004,
        liquidity_usd=50_000.0,
        strategy="early_discovery",
        is_exit=False,
    )
    base.update(over)
    return TradeIntent(**base)


# --------------------------- базовый allow ---------------------------

def test_clean_buy_allowed():
    d = evaluate(_buy(), _policy(), _portfolio(), now=NOW)
    assert d.allowed, d.reasons
    assert d.reasons == ()
    assert d.verdict == "ALLOW"
    assert d.policy_version == "test-v1"


def test_decision_is_deterministic():
    a = evaluate(_buy(), _policy(), _portfolio(), now=NOW)
    b = evaluate(_buy(), _policy(), _portfolio(), now=NOW)
    assert a.verdict == b.verdict
    assert [r.code for r in a.reasons] == [r.code for r in b.reasons]


# --------------------------- размер/экспозиция (AC-07) ---------------------------

def test_position_size_over_limit_blocked():
    # 2000 USD = 2% equity > лимита 1%
    d = evaluate(_buy(notional_usd=2_000.0), _policy(), _portfolio(), now=NOW)
    assert d.blocked
    assert any(r.code == "position_size_exceeded" for r in d.reasons)


def test_aggregate_exposure_over_limit_blocked():
    # уже открыто 19.8% equity, новая сделка на 0.5% → суммарно >20%
    held = (Position("eth:0xheld", notional_usd=19_800.0),)
    d = evaluate(_buy(notional_usd=500.0), _policy(),
                 _portfolio(open_positions=held), now=NOW)
    assert d.blocked
    assert any(r.code == "exposure_exceeded" for r in d.reasons)


def test_max_open_positions_blocked():
    held = tuple(Position(f"eth:0x{i}", notional_usd=100.0) for i in range(5))
    d = evaluate(_buy(), _policy(max_open_positions=5),
                 _portfolio(open_positions=held), now=NOW)
    assert d.blocked
    assert any(r.code == "max_open_positions" for r in d.reasons)


# --------------------------- маршрут/котировка ---------------------------

def test_slippage_over_limit_blocked():
    d = evaluate(_buy(expected_slippage_pct=0.05), _policy(), _portfolio(), now=NOW)
    assert d.blocked
    assert any(r.code == "slippage_exceeded" for r in d.reasons)


def test_unknown_slippage_blocked_fail_closed():
    d = evaluate(_buy(expected_slippage_pct=None), _policy(), _portfolio(), now=NOW)
    assert d.blocked
    assert any(r.code == "slippage_unknown" for r in d.reasons)


def test_low_liquidity_blocked():
    d = evaluate(_buy(liquidity_usd=1_000.0), _policy(), _portfolio(), now=NOW)
    assert d.blocked
    assert any(r.code == "liquidity_too_low" for r in d.reasons)


def test_unknown_liquidity_blocked_fail_closed():
    d = evaluate(_buy(liquidity_usd=None), _policy(), _portfolio(), now=NOW)
    assert d.blocked
    assert any(r.code == "liquidity_unknown" for r in d.reasons)


def test_stale_quote_blocked():
    d = evaluate(_buy(quote_age_seconds=120.0), _policy(), _portfolio(), now=NOW)
    assert d.blocked
    assert any(r.code == "quote_too_old" for r in d.reasons)


def test_unknown_quote_age_blocked_fail_closed():
    d = evaluate(_buy(quote_age_seconds=None), _policy(), _portfolio(), now=NOW)
    assert d.blocked
    assert any(r.code == "quote_age_unknown" for r in d.reasons)


# --------------------------- безопасность (AC-08) ---------------------------

@pytest.mark.parametrize("verdict", ["REVIEW", "BLOCK", "UNKNOWN", None])
def test_non_pass_safety_verdict_blocked(verdict):
    d = evaluate(_buy(safety_verdict=verdict), _policy(), _portfolio(), now=NOW)
    assert d.blocked
    assert any(r.code == "safety_not_passed" for r in d.reasons)


# --------------------------- дневной лимит убытка ---------------------------

def test_daily_loss_limit_breached_blocks_new_entries():
    # equity 100k, лимит 2% = 2000. Уже −2500 за день → новые входы запрещены.
    d = evaluate(_buy(), _policy(),
                 _portfolio(realized_pnl_today_usd=-2_500.0), now=NOW)
    assert d.blocked
    assert any(r.code == "daily_loss_limit" for r in d.reasons)


def test_small_daily_loss_still_allows():
    d = evaluate(_buy(), _policy(),
                 _portfolio(realized_pnl_today_usd=-100.0), now=NOW)
    assert d.allowed, d.reasons


# --------------------------- потеря данных (fail-closed) ---------------------------

def test_stale_data_blocks_new_entries():
    d = evaluate(_buy(), _policy(), _portfolio(data_fresh=False), now=NOW)
    assert d.blocked
    assert any(r.code == "market_data_stale" for r in d.reasons)


# --------------------------- выходы (SELL) ---------------------------

def test_exit_sell_allowed_with_fresh_data():
    intent = _buy(side="SELL", is_exit=True, recipient="0xOWNER",
                  safety_verdict=None, liquidity_usd=None,
                  expected_slippage_pct=None, quote_age_seconds=None)
    d = evaluate(intent, _policy(), _portfolio(), now=NOW)
    # выход не блокируется входными гейтами (safety/liquidity/slippage),
    # поскольку закрытие позиции — это безопасный путь, а не новый вход.
    assert d.allowed, d.reasons


def test_exit_sell_blocked_when_data_stale():
    # Нельзя бесконтрольно продавать при отсутствии достоверных котировок (ТЗ §6).
    intent = _buy(side="SELL", is_exit=True)
    d = evaluate(intent, _policy(), _portfolio(data_fresh=False), now=NOW)
    assert d.blocked
    assert any(r.code == "market_data_stale" for r in d.reasons)


# --------------------------- несколько нарушений разом ---------------------------

def test_multiple_violations_all_reported():
    intent = _buy(notional_usd=5_000.0, safety_verdict="REVIEW",
                  liquidity_usd=100.0, expected_slippage_pct=0.5)
    d = evaluate(intent, _policy(), _portfolio(), now=NOW)
    assert d.blocked
    codes = {r.code for r in d.reasons}
    assert {"position_size_exceeded", "safety_not_passed",
            "liquidity_too_low", "slippage_exceeded"} <= codes
