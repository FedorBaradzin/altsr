"""Калибровка confidence на исходах (T3): разделение win/loss, fallback."""
from __future__ import annotations

from app.signals.calibration import (
    N_FEATURES,
    Weights,
    accuracy,
    extract_features,
    fit_logistic,
    predict_proba,
)


def _dataset():
    """Синтетика: win когда roc_m5 высокий И давление покупок есть."""
    x: list[list[float]] = []
    y: list[int] = []
    for i in range(60):
        roc = -10.0 + (i % 20)          # от −10 до +9
        buys = 20 if i % 2 == 0 else 3
        sells = 5
        feats = extract_features(
            roc_m5=roc, roc_h1=roc / 2, buys_m5=buys, sells_m5=sells,
            liquidity_usd=50_000, risk_score=10, vol_h1=120_000,
        )
        x.append(feats)
        y.append(1 if (roc >= 3 and buys > sells) else 0)
    return x, y


def test_extract_features_shape_and_neutral():
    f = extract_features(roc_m5=None, roc_h1=None, buys_m5=None, sells_m5=None,
                         liquidity_usd=None, risk_score=None, vol_h1=None)
    assert len(f) == N_FEATURES
    assert f[2] == 1.0   # нейтральный buy/sell
    assert f[4] == 0.5   # нейтральный risk_inv


def test_fit_separates_win_loss():
    x, y = _dataset()
    w = fit_logistic(x, y, epochs=800, lr=0.3)
    assert w is not None
    assert accuracy(x, y, w) >= 0.8


def test_fit_returns_none_on_too_few_samples():
    x, y = _dataset()
    assert fit_logistic(x[:5], y[:5], min_samples=20) is None


def test_fit_returns_none_on_single_class():
    x, y = _dataset()
    assert fit_logistic(x, [1] * len(y)) is None


def test_predict_proba_bounds():
    w = Weights(bias=0.0, coef=tuple([0.0] * N_FEATURES))
    assert predict_proba([0.0] * N_FEATURES, w) == 0.5
    w2 = Weights(bias=10.0, coef=tuple([0.0] * N_FEATURES))
    assert predict_proba([0.0] * N_FEATURES, w2) > 0.99


def test_weights_validate_dimension():
    import pytest
    with pytest.raises(ValueError):
        Weights(bias=0.0, coef=(1.0, 2.0))


def test_evaluate_entry_uses_calibrated_confidence_when_enabled():
    from app.config import get_settings
    from app.signals.engine import SignalInput, evaluate_entry

    s = get_settings()
    s.momentum_enabled = False
    s.indicators_enabled = False
    s.calibration_enabled = True
    inp = SignalInput(chain="eth", address="0x", liquidity_usd=8000.0,
                      age_minutes=30.0, verdict="PASS", risk_score=10,
                      price_change_m5=5.0, price_change_h1=3.0, buys_m5=20, sells_m5=5)
    # Сильно положительное смещение → высокая confidence из весов.
    w = Weights(bias=5.0, coef=tuple([0.0] * N_FEATURES))
    d = evaluate_entry(inp, s, weights=w)
    assert d.passed
    assert d.confidence > 0.99

    # Без весов (калибровки нет) — эвристика, другое значение.
    d2 = evaluate_entry(inp, s)
    assert d2.confidence <= 1.0
