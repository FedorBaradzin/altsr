"""Проверка ограниченных полномочий делегации (ТЗ §2.1).

Критерии приёмки:
- AC-03 — отозванная/истёкшая делегация не может совершать новые операции.
- AC-06 — запрет перевода средств неразрешённому адресу.
- AC-07 — запрет превышения лимита расходов (на сделку и дневного).

Эти проверки встроены в единый гейт Risk Engine (одна точка решения).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.risk.delegation import DelegationPolicy, SpendState
from app.risk.engine import evaluate
from app.risk.policy import RiskPolicy
from app.risk.types import PortfolioState, TradeIntent

NOW = datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc)


def _policy() -> RiskPolicy:
    return RiskPolicy(
        version="test-v1", max_position_pct=1.0, max_exposure_pct=1.0,
        daily_loss_limit_pct=1.0, max_open_positions=100, max_slippage_pct=1.0,
        min_liquidity_usd=0.0, max_quote_age_seconds=1e9,
    )


def _portfolio() -> PortfolioState:
    return PortfolioState(equity_usd=100_000.0, data_fresh=True)


def _buy(**over) -> TradeIntent:
    base = dict(
        side="BUY", token_key="eth:0xabc", chain="eth", token_address="0xabc",
        notional_usd=500.0, recipient="0xOWNER", safety_verdict="PASS",
        quote_age_seconds=5.0, expected_slippage_pct=0.004, liquidity_usd=50_000.0,
        strategy="early_discovery", is_exit=False,
    )
    base.update(over)
    return TradeIntent(**base)


def _delegation(**over) -> DelegationPolicy:
    base = dict(
        delegation_id="d1",
        owner="0xOWNER",
        revoked=False,
        expires_at=NOW + timedelta(days=1),
        allowed_chains=("eth",),
        allowed_tokens=(),               # пусто = любой токен (решает Safety Engine)
        allowed_recipients=(),           # пусто = только владелец
        allowed_strategies=("early_discovery",),
        max_trade_usd=1_000.0,
        daily_cap_usd=5_000.0,
        weekly_cap_usd=20_000.0,
    )
    base.update(over)
    return DelegationPolicy(**base)


def _eval(intent, delegation, spent=None):
    return evaluate(intent, _policy(), _portfolio(),
                    delegation=delegation, spent=spent or SpendState(), now=NOW)


# --------------------------- чистый случай ---------------------------

def test_clean_delegated_buy_allowed():
    d = _eval(_buy(), _delegation())
    assert d.allowed, d.reasons


# --------------------------- отзыв / истечение (AC-03) ---------------------------

def test_revoked_delegation_blocked():
    d = _eval(_buy(), _delegation(revoked=True))
    assert d.blocked
    assert any(r.code == "delegation_revoked" for r in d.reasons)


def test_expired_delegation_blocked():
    d = _eval(_buy(), _delegation(expires_at=NOW - timedelta(seconds=1)))
    assert d.blocked
    assert any(r.code == "delegation_expired" for r in d.reasons)


# --------------------------- получатель (AC-06) ---------------------------

def test_arbitrary_recipient_blocked():
    d = _eval(_buy(recipient="0xATTACKER"), _delegation())
    assert d.blocked
    assert any(r.code == "recipient_not_allowed" for r in d.reasons)


def test_allowlisted_recipient_ok():
    d = _eval(_buy(recipient="0xPAYOUT"),
              _delegation(allowed_recipients=("0xPAYOUT",)))
    assert d.allowed, d.reasons


def test_recipient_check_case_insensitive():
    d = _eval(_buy(recipient="0xowner"), _delegation(owner="0xOWNER"))
    assert d.allowed, d.reasons


# --------------------------- лимиты расходов (AC-07) ---------------------------

def test_per_trade_cap_exceeded_blocked():
    d = _eval(_buy(notional_usd=2_000.0), _delegation(max_trade_usd=1_000.0))
    assert d.blocked
    assert any(r.code == "trade_cap_exceeded" for r in d.reasons)


def test_daily_cap_exceeded_blocked():
    # уже потрачено 4800 сегодня, новая сделка 500 → 5300 > дневного лимита 5000
    d = _eval(_buy(notional_usd=500.0), _delegation(daily_cap_usd=5_000.0),
              spent=SpendState(spent_today_usd=4_800.0))
    assert d.blocked
    assert any(r.code == "daily_cap_exceeded" for r in d.reasons)


def test_weekly_cap_exceeded_blocked():
    d = _eval(_buy(notional_usd=500.0), _delegation(weekly_cap_usd=20_000.0),
              spent=SpendState(spent_week_usd=19_800.0))
    assert d.blocked
    assert any(r.code == "weekly_cap_exceeded" for r in d.reasons)


# --------------------------- allowlists / стратегия ---------------------------

def test_chain_not_allowlisted_blocked():
    d = _eval(_buy(chain="bsc"), _delegation(allowed_chains=("eth",)))
    assert d.blocked
    assert any(r.code == "chain_not_allowed" for r in d.reasons)


def test_empty_chain_allowlist_denies():
    # пустой список сетей = ни одна сеть не разрешена (fail-closed).
    d = _eval(_buy(), _delegation(allowed_chains=()))
    assert d.blocked
    assert any(r.code == "chain_not_allowed" for r in d.reasons)


def test_token_not_in_nonempty_allowlist_blocked():
    d = _eval(_buy(token_key="eth:0xabc"),
              _delegation(allowed_tokens=("eth:0xOTHER",)))
    assert d.blocked
    assert any(r.code == "token_not_allowed" for r in d.reasons)


def test_strategy_not_permitted_blocked():
    d = _eval(_buy(strategy="breakout"),
              _delegation(allowed_strategies=("early_discovery",)))
    assert d.blocked
    assert any(r.code == "strategy_not_allowed" for r in d.reasons)


def test_empty_strategy_allowlist_denies():
    d = _eval(_buy(), _delegation(allowed_strategies=()))
    assert d.blocked
    assert any(r.code == "strategy_not_allowed" for r in d.reasons)


# --------------------------- выход не тратит бюджет ---------------------------

def test_exit_sell_not_subject_to_spend_caps():
    # Продажа возвращает средства владельцу — не расходует торговый бюджет,
    # но получатель всё равно должен быть владельцем/разрешённым.
    intent = _buy(side="SELL", is_exit=True, notional_usd=50_000.0,
                  recipient="0xOWNER")
    d = _eval(intent, _delegation(max_trade_usd=1_000.0))
    assert d.allowed, d.reasons


def test_exit_sell_to_arbitrary_recipient_blocked():
    intent = _buy(side="SELL", is_exit=True, recipient="0xATTACKER")
    d = _eval(intent, _delegation())
    assert d.blocked
    assert any(r.code == "recipient_not_allowed" for r in d.reasons)
