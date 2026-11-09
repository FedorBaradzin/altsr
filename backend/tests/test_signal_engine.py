"""Ворота входа signal engine: пропуск, отказы, уверенность."""
from __future__ import annotations

from app.config import get_settings
from app.signals.engine import SignalInput, evaluate_entry


def _s():
    return get_settings()


def _ok(**kw) -> SignalInput:
    base = dict(chain="ethereum", address="0xabc", liquidity_usd=8000.0,
                age_minutes=30.0, holder_count=None, verdict="PASS", risk_score=10)
    base.update(kw)
    return SignalInput(**base)


def test_clean_input_passes():
    d = evaluate_entry(_ok(), _s())
    assert d.passed is True
    assert 0.0 < d.confidence <= 1.0
    assert any("PASS" in r for r in d.reasons)


def test_reject_non_pass_verdict():
    d = evaluate_entry(_ok(verdict="REVIEW"), _s())
    assert not d.passed
    assert "REVIEW" in d.rejected


def test_reject_missing_safety():
    d = evaluate_entry(_ok(verdict=None), _s())
    assert not d.passed
    assert "safety" in d.rejected


def test_reject_low_liquidity():
    d = evaluate_entry(_ok(liquidity_usd=1000.0), _s())
    assert not d.passed
    assert "ликвидность" in d.rejected


def test_reject_unknown_liquidity():
    d = evaluate_entry(_ok(liquidity_usd=None), _s())
    assert not d.passed


def test_reject_too_old():
    s = _s()
    s.signal_max_age_minutes = 60
    d = evaluate_entry(_ok(age_minutes=120.0), s)
    assert not d.passed
    assert "старый" in d.rejected


def test_reject_high_risk():
    s = _s()
    s.signal_max_risk = 20
    d = evaluate_entry(_ok(risk_score=25), s)
    assert not d.passed


def test_holders_gate_when_required():
    s = _s()
    s.signal_min_holders = 100
    assert not evaluate_entry(_ok(holder_count=None), s).passed
    assert not evaluate_entry(_ok(holder_count=40), s).passed
    assert evaluate_entry(_ok(holder_count=150), s).passed


def test_confidence_rises_with_lower_risk_and_more_liquidity():
    s = _s()
    low = evaluate_entry(_ok(risk_score=28, liquidity_usd=5000.0), s).confidence
    high = evaluate_entry(_ok(risk_score=2, liquidity_usd=50000.0, holder_count=500), s).confidence
    assert high > low
