"""Проводка volume-spike в движок входа: флаг, вклад в уверенность, ворота.

По умолчанию vol_spike_enabled=False → поведение не меняется (проверяем явно).
Все изменения Settings восстанавливаем (get_settings кэшируется).

ВАЖНО: всплеск улучшает ранжирование/ожидаемую ценность входа, не гарантирует рост.
"""
from __future__ import annotations

from contextlib import contextmanager

from app.config import get_settings
from app.signals.engine import SignalInput, evaluate_entry


@contextmanager
def _settings(**overrides):
    s = get_settings()
    saved = {k: getattr(s, k) for k in overrides}
    for k, v in overrides.items():
        setattr(s, k, v)
    try:
        yield s
    finally:
        for k, v in saved.items():
            setattr(s, k, v)


def _inp(**kw) -> SignalInput:
    base = dict(
        chain="ethereum", address="0xabc", liquidity_usd=20000.0,
        age_minutes=30.0, holder_count=50, verdict="PASS", risk_score=15,
    )
    base.update(kw)
    return SignalInput(**base)


# Вход со всплеском: vol_h1=3000, предыдущие 5ч ~1000/ч ((8000-3000)/5) → всплеск 3×.
_SPIKE = dict(vol_h1=3000.0, vol_h6=8000.0)
# Тот же оборот vol_h1, но без всплеска (ровный объём): prior5 = (16000-3000)/5=2600 → 1.15×.
_FLAT = dict(vol_h1=3000.0, vol_h6=16000.0)


def test_spike_disabled_by_default_does_not_change_confidence():
    # Флаг по умолчанию ВЫКЛ → всплеск не влияет: confidence равны.
    with _settings(momentum_enabled=False):
        spike = evaluate_entry(_inp(**_SPIKE), get_settings()).confidence
        flat = evaluate_entry(_inp(**_FLAT), get_settings()).confidence
    assert spike == flat


def test_spike_adds_confidence_when_enabled():
    with _settings(momentum_enabled=False, vol_spike_enabled=True,
                   signal_conf_w_vol_spike=0.10):
        spike = evaluate_entry(_inp(**_SPIKE), get_settings()).confidence
        flat = evaluate_entry(_inp(**_FLAT), get_settings()).confidence
    assert spike > flat


def test_spike_gate_rejects_below_min():
    with _settings(momentum_enabled=False, vol_spike_enabled=True,
                   signal_vol_spike_min=2.0):
        d = evaluate_entry(_inp(**_FLAT), get_settings())  # всплеск ~1.15× < 2×
    assert not d.passed
    assert "всплеск объёма" in (d.rejected or "")


def test_spike_gate_passes_above_min():
    with _settings(momentum_enabled=False, vol_spike_enabled=True,
                   signal_vol_spike_min=2.0):
        d = evaluate_entry(_inp(**_SPIKE), get_settings())  # всплеск 3× ≥ 2×
    assert d.passed
    assert any("всплеск объёма" in r for r in d.reasons)


def test_spike_gate_graceful_without_data():
    # Нет данных для базы всплеска → ворота НЕ отсекают ранний токен.
    with _settings(momentum_enabled=False, vol_spike_enabled=True,
                   signal_vol_spike_min=3.0):
        d = evaluate_entry(_inp(vol_h1=3000.0), get_settings())  # ни vol_h6, ни prev
    assert d.passed


def test_spike_gate_off_when_min_zero():
    # Флаг включён, но min=0 → ворот нет (только вклад в уверенность).
    with _settings(momentum_enabled=False, vol_spike_enabled=True,
                   signal_vol_spike_min=0.0):
        d = evaluate_entry(_inp(**_FLAT), get_settings())
    assert d.passed
