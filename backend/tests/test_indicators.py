"""Технические индикаторы (T1) — известные ряды → известные значения."""
from __future__ import annotations

import pytest

from app.signals.indicators import aroon, aroon_osc, atr, roc, true_ranges


def test_roc_basic():
    assert roc([10, 11, 12], 1) == pytest.approx(9.0909, abs=1e-3)
    assert roc([10, 11, 12], 2) == pytest.approx(20.0)
    # Падение → отрицательный ROC.
    assert roc([12, 11, 10], 1) == pytest.approx(-9.0909, abs=1e-3)


def test_roc_validation():
    with pytest.raises(ValueError):
        roc([10, 11], 5)        # мало данных
    with pytest.raises(ValueError):
        roc([0, 5], 1)          # нулевая база
    with pytest.raises(ValueError):
        roc([1, 2, 3], 0)       # n < 1


def test_true_ranges_and_atr():
    highs = [10, 12, 14]
    lows = [8, 9, 11]
    closes = [9, 11, 13]
    assert true_ranges(highs, lows, closes) == [3.0, 3.0]
    assert atr(highs, lows, closes, 2) == pytest.approx(3.0)


def test_atr_validation():
    with pytest.raises(ValueError):
        atr([1, 2], [1, 2], [1, 2], 5)       # мало баров
    with pytest.raises(ValueError):
        atr([1, 2, 3], [1, 2], [1, 2, 3], 1)  # разная длина


def test_aroon_uptrend():
    up, down = aroon([1, 2, 3], [1, 2, 3], 2)
    assert up == pytest.approx(100.0)
    assert down == pytest.approx(0.0)
    assert aroon_osc([1, 2, 3], [1, 2, 3], 2) == pytest.approx(100.0)


def test_aroon_downtrend():
    assert aroon_osc([3, 2, 1], [3, 2, 1], 2) == pytest.approx(-100.0)


def test_aroon_flat_no_trend():
    assert aroon_osc([2, 2, 2], [2, 2, 2], 2) == pytest.approx(0.0)


def test_aroon_validation():
    with pytest.raises(ValueError):
        aroon([1, 2], [1, 2], 5)
    with pytest.raises(ValueError):
        aroon([1, 2, 3], [1, 2], 2)
