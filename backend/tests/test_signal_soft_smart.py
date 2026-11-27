"""Мягкое условие входа по smart-money (SIGNAL_SOFT_SMART_ENABLED).

Среди прошедших базовые ворота берём вход только если ЕСТЬ smart-money ИЛИ свежий
сильный моментум m5. Иначе — отказ ("доехавший"/слабый памп). Жёсткий гейт выключен.
"""
from __future__ import annotations

from app.config import get_settings
from app.signals.engine import SignalInput, evaluate_entry


def _s():
    s = get_settings()
    # Изолируем мягкое условие от прочих ворот.
    s.momentum_enabled = False
    s.indicators_enabled = False
    s.vol_spike_enabled = False
    s.signal_require_smart_money = False
    s.signal_soft_smart_enabled = True
    s.signal_soft_min_smart_wallets = 1
    s.signal_soft_strong_m5 = 3.0
    return s


def _ok(**kw) -> SignalInput:
    base = dict(chain="ethereum", address="0xabc", liquidity_usd=50000.0,
                age_minutes=60.0, holder_count=None, verdict="PASS", risk_score=10)
    base.update(kw)
    return SignalInput(**base)


def test_soft_reject_no_smart_weak_m5():
    d = evaluate_entry(_ok(smart_wallets=0, price_change_m5=1.0), _s())
    assert not d.passed
    assert "smart-money" in d.rejected


def test_soft_pass_strong_m5_without_smart():
    d = evaluate_entry(_ok(smart_wallets=0, price_change_m5=5.0), _s())
    assert d.passed
    assert any("сильный моментум" in r for r in d.reasons)


def test_soft_pass_smart_with_weak_m5():
    d = evaluate_entry(_ok(smart_wallets=2, price_change_m5=1.0), _s())
    assert d.passed
    assert any("smart-money" in r for r in d.reasons)


def test_soft_disabled_is_inert():
    s = _s()
    s.signal_soft_smart_enabled = False
    d = evaluate_entry(_ok(smart_wallets=0, price_change_m5=1.0), s)
    assert d.passed  # без мягкого условия слабый вход проходит (как раньше)
