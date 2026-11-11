"""Чистые функции рыночной динамики (volume-spike + buy-pressure).

volume_spike_ratio — во сколько раз текущий часовой объём превышает базовый
(средний за предыдущие часы). Это ОТЛИЧАЕТСЯ от оборота vol/liq и от булева
«объём растёт»: ловит именно всплеск активности. Все функции без БД/сети.

ВАЖНО: всплеск объёма повышает ожидаемую ценность/ранжирование входа,
а не гарантирует прибыль (большинство новых токенов идут в ноль).
"""
from __future__ import annotations

import pytest

from app.signals.momentum_features import (
    buy_pressure_ratio,
    volume_spike_bonus,
    volume_spike_ratio,
)

# --- buy_pressure_ratio ---

def test_buy_pressure_ratio_enough_trades():
    assert buy_pressure_ratio(20, 5) == pytest.approx(4.0)


def test_buy_pressure_ratio_too_few_trades_is_none():
    # Меньше min_trades сделок → отношение статистически незначимо.
    assert buy_pressure_ratio(2, 1) is None


def test_buy_pressure_ratio_zero_sells_no_div_error():
    # Делитель защищён max(1, sells): все покупки → ratio == buys.
    assert buy_pressure_ratio(10, 0) == pytest.approx(10.0)


def test_buy_pressure_ratio_missing_data_is_none():
    assert buy_pressure_ratio(None, 5) is None
    assert buy_pressure_ratio(10, None) is None


# --- volume_spike_ratio ---

def test_spike_ratio_from_h6_baseline():
    # Предыдущие 5ч = (vol_h6 - vol_h1)/5 = (8000-3000)/5 = 1000; ratio = 3000/1000 = 3.0.
    assert volume_spike_ratio(3000.0, vol_h6=8000.0) == pytest.approx(3.0)


def test_spike_ratio_fallback_to_prev_hour():
    # vol_h6 нет → базой служит предыдущий срез h1.
    assert volume_spike_ratio(2000.0, vol_h6=None, vol_h1_prev=1000.0) == pytest.approx(2.0)


def test_spike_ratio_prefers_h6_over_prev():
    # Есть оба источника базы → используем усреднённые предыдущие часы (h6).
    assert volume_spike_ratio(3000.0, vol_h6=8000.0, vol_h1_prev=50.0) == pytest.approx(3.0)


def test_spike_ratio_none_without_baseline():
    assert volume_spike_ratio(3000.0, vol_h6=None, vol_h1_prev=None) is None


def test_spike_ratio_none_when_h6_not_greater_than_h1_and_no_prev():
    # Вырожденные данные (h6 <= h1) и нет prev → базы нет.
    assert volume_spike_ratio(5000.0, vol_h6=5000.0) is None


def test_spike_ratio_none_when_vol_h1_missing():
    assert volume_spike_ratio(None, vol_h6=8000.0) is None


# --- volume_spike_bonus ---

def test_spike_bonus_zero_at_or_below_unity():
    assert volume_spike_bonus(1.0, ref=3.0, weight=0.10) == pytest.approx(0.0)
    assert volume_spike_bonus(0.5, ref=3.0, weight=0.10) == pytest.approx(0.0)


def test_spike_bonus_full_at_or_above_ref():
    assert volume_spike_bonus(3.0, ref=3.0, weight=0.10) == pytest.approx(0.10)
    assert volume_spike_bonus(9.0, ref=3.0, weight=0.10) == pytest.approx(0.10)


def test_spike_bonus_is_monotonic_between():
    low = volume_spike_bonus(1.5, ref=3.0, weight=0.10)
    high = volume_spike_bonus(2.5, ref=3.0, weight=0.10)
    assert 0.0 < low < high < 0.10


def test_spike_bonus_none_ratio_is_zero():
    assert volume_spike_bonus(None, ref=3.0, weight=0.10) == pytest.approx(0.0)
