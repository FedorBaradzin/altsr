"""Гейт входа по индикаторам (T1): растущий проходит, плоский/падающий — нет.

Моментум отключён (тестируется отдельно); проверяем именно индикаторный слой.
Периоды Aroon/ATR уменьшены до 2 — пороги берутся из конфига.
"""
from __future__ import annotations

from app.config import get_settings
from app.signals.engine import SignalInput, evaluate_entry


def _s(**over):
    s = get_settings()
    s.momentum_enabled = False
    s.indicators_enabled = True
    s.indicator_aroon_period = 2
    s.indicator_atr_period = 2
    for k, v in over.items():
        setattr(s, k, v)
    return s


def _ok(**kw) -> SignalInput:
    base = dict(chain="ethereum", address="0xabc", liquidity_usd=8000.0,
                age_minutes=30.0, verdict="PASS", risk_score=10)
    base.update(kw)
    return SignalInput(**base)


# Растущие ряды длины 3 (хватает при period=2).
RISING = dict(
    closes=[100.0, 110.0, 121.0],
    highs=[101.0, 112.0, 123.0],
    lows=[99.0, 109.0, 120.0],
    vol_h1=200_000.0, vol_h1_prev=100_000.0,
    buys_m5=20, sells_m5=5,
)


def test_rising_token_passes():
    d = evaluate_entry(_ok(**RISING), _s())
    assert d.passed
    assert any("ROC" in r for r in d.reasons)
    assert any("aroon_osc" in r for r in d.reasons)
    assert any("ATR" in r for r in d.reasons)


def test_falling_token_rejected_on_roc():
    falling = dict(RISING)
    falling["closes"] = [121.0, 110.0, 100.0]
    d = evaluate_entry(_ok(**falling), _s(indicator_roc_min=0.0))
    assert not d.passed
    assert "ROC" in d.rejected


def test_flat_token_rejected_on_atr_cost_floor():
    flat = dict(
        closes=[100.0, 100.0, 100.0],
        highs=[100.0, 100.0, 100.0],
        lows=[100.0, 100.0, 100.0],
        vol_h1=200_000.0, vol_h1_prev=100_000.0,
        buys_m5=20, sells_m5=5,
    )
    d = evaluate_entry(_ok(**flat), _s())
    assert not d.passed
    assert "ATR" in d.rejected


def test_volume_not_rising_rejected():
    stale = dict(RISING)
    stale["vol_h1"] = 100_000.0
    stale["vol_h1_prev"] = 100_000.0
    d = evaluate_entry(_ok(**stale), _s())
    assert not d.passed
    assert "объём" in d.rejected


def test_weak_buy_pressure_rejected():
    weak = dict(RISING)
    weak["buys_m5"] = 3
    weak["sells_m5"] = 10
    d = evaluate_entry(_ok(**weak), _s(indicator_buy_sell_min=1.3))
    assert not d.passed
    assert "buys/sells" in d.rejected


def test_aroon_threshold_rejects_weak_trend():
    # Требуем сильный тренд; слабый ряд не дотягивает.
    weak_trend = dict(
        closes=[100.0, 101.0, 100.5],
        highs=[101.0, 102.0, 101.0],
        lows=[99.0, 100.0, 100.0],
        vol_h1=200_000.0, vol_h1_prev=100_000.0,
        buys_m5=20, sells_m5=5,
    )
    d = evaluate_entry(_ok(**weak_trend), _s(indicator_aroon_osc_min=90.0,
                                             indicator_cost_floor_pct=0.0,
                                             indicator_roc_min=-100.0))
    assert not d.passed
    assert "aroon_osc" in d.rejected


def test_missing_series_skipped_when_not_required():
    # Нет рядов, require_data=False → индикаторный гейт не мешает.
    d = evaluate_entry(_ok(), _s(indicators_require_data=False,
                                 indicator_require_vol_rising=False))
    assert d.passed


def test_missing_series_blocks_when_required():
    d = evaluate_entry(_ok(), _s(indicators_require_data=True))
    assert not d.passed
    assert "нет данных индикатора" in d.rejected
