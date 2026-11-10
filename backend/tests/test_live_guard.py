"""Предохранители живого исполнения: по умолчанию ничего не исполняется."""
from __future__ import annotations

import pytest

from app.config import get_settings
from app.live.executor import (
    LiveTradingDisabled,
    attempt_live_buy,
    preflight,
)
from app.risk.killswitch import KillSwitchState, trip


def _enabled_settings():
    s = get_settings()
    s.live_trading_enabled = True
    s.live_wallet_address = "0xwallet"
    s.live_private_rpc = "https://rpc"
    s.live_daily_cap_usd = 1000
    s.live_max_trade_usd = 100
    s.live_require_confirmation = True
    return s


def test_disabled_by_default():
    s = get_settings()  # live_trading_enabled=False
    pf = preflight(s, verdict="PASS", honeypot_ok=True, trade_usd=50, confirmed=True)
    assert not pf.allowed
    assert "выключена" in pf.reason


def test_enabled_but_no_wallet_refuses():
    s = get_settings()
    s.live_trading_enabled = True
    pf = preflight(s, verdict="PASS", honeypot_ok=True, trade_usd=50, confirmed=True)
    assert not pf.allowed


def test_non_pass_refused():
    pf = preflight(_enabled_settings(), verdict="REVIEW", honeypot_ok=True, trade_usd=50, confirmed=True)
    assert not pf.allowed


def test_honeypot_fail_refused():
    pf = preflight(_enabled_settings(), verdict="PASS", honeypot_ok=False, trade_usd=50, confirmed=True)
    assert not pf.allowed


def test_over_trade_limit_refused():
    pf = preflight(_enabled_settings(), verdict="PASS", honeypot_ok=True, trade_usd=500, confirmed=True)
    assert not pf.allowed


def test_no_confirmation_refused():
    pf = preflight(_enabled_settings(), verdict="PASS", honeypot_ok=True, trade_usd=50, confirmed=False)
    assert not pf.allowed


def test_killswitch_active_refuses_even_when_all_gates_pass():
    # Аварийная остановка перекрывает все пройденные предохранители (ТЗ §6, AC-15).
    ks = trip("admin_manual")
    pf = preflight(_enabled_settings(), verdict="PASS", honeypot_ok=True,
                   trade_usd=50, confirmed=True, killswitch=ks)
    assert not pf.allowed
    assert "аварийная остановка" in pf.reason


def test_killswitch_inactive_does_not_block():
    pf = preflight(_enabled_settings(), verdict="PASS", honeypot_ok=True,
                   trade_usd=50, confirmed=True, killswitch=KillSwitchState(active=False))
    assert pf.allowed


async def test_attempt_live_buy_killswitch_refuses():
    with pytest.raises(LiveTradingDisabled):
        await attempt_live_buy(_enabled_settings(), verdict="PASS", honeypot_ok=True,
                               trade_usd=50, confirmed=True, killswitch=trip("admin_manual"))


async def test_attempt_live_buy_disabled_raises():
    s = get_settings()
    with pytest.raises(LiveTradingDisabled):
        await attempt_live_buy(s, verdict="PASS", honeypot_ok=True, trade_usd=50, confirmed=True)


async def test_all_gates_pass_but_swap_not_wired():
    # Даже когда все предохранители пройдены, реальный своп намеренно не подключён.
    s = _enabled_settings()
    with pytest.raises(NotImplementedError):
        await attempt_live_buy(s, verdict="PASS", honeypot_ok=True, trade_usd=50, confirmed=True)
