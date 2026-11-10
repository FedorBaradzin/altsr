"""Динамическая уверенность входа: моментум, давление покупок, оборот.

Гейты входа не меняются — momentum_enabled=False, чтобы и «растущий», и
«плоский» входы ПРОШЛИ ворота, и мы сравнивали именно их confidence.

ВАЖНО: тесты проверяют ранжирование/ожидаемую ценность, а не «прибыль».
"""
from __future__ import annotations

from app.config import get_settings
from app.signals.engine import SignalInput, evaluate_entry


def _s():
    s = get_settings()
    # Ворота моментума отключены: сравниваем confidence прошедших входов,
    # не отсеивая «плоский/падающий» вход на этапе гейтов.
    s.momentum_enabled = False
    return s


def _inp(**kw) -> SignalInput:
    base = dict(
        chain="ethereum", address="0xabc", liquidity_usd=20000.0,
        age_minutes=30.0, holder_count=50, verdict="PASS", risk_score=15,
    )
    base.update(kw)
    return SignalInput(**base)


def test_positive_momentum_and_buy_pressure_beat_flat():
    s = _s()
    # Растёт + сильный перевес покупок + здоровый оборот.
    hot = evaluate_entry(
        _inp(price_change_m5=8.0, price_change_h1=40.0,
             buys_m5=30, sells_m5=5, vol_h1=20000.0),
        s,
    )
    # Тот же вход, но плоский/падающий и с перевесом продаж.
    flat = evaluate_entry(
        _inp(price_change_m5=-2.0, price_change_h1=0.0,
             buys_m5=5, sells_m5=20, vol_h1=20000.0),
        s,
    )
    assert hot.passed and flat.passed
    assert hot.confidence > flat.confidence


def test_stronger_momentum_monotonic():
    s = _s()
    mild = evaluate_entry(_inp(price_change_m5=2.0, price_change_h1=10.0), s).confidence
    strong = evaluate_entry(_inp(price_change_m5=9.0, price_change_h1=45.0), s).confidence
    assert strong > mild


def test_buy_pressure_above_ref_adds_confidence():
    s = _s()
    weak = evaluate_entry(_inp(buys_m5=5, sells_m5=5), s).confidence     # ratio 1.0 < 1.3
    strong = evaluate_entry(_inp(buys_m5=20, sells_m5=5), s).confidence  # ratio 4.0 > 1.3
    assert strong > weak


def test_confidence_stays_in_unit_interval_extremes():
    s = _s()
    # Экстремально «хороший» вход не должен выходить за 1.0.
    best = evaluate_entry(
        _inp(risk_score=0, liquidity_usd=10_000_000.0, holder_count=100000,
             price_change_m5=500.0, price_change_h1=500.0,
             buys_m5=10000, sells_m5=1, vol_h1=10_000_000.0),
        s,
    )
    # Экстремально «плохой» (но прошедший ворота) вход не уходит ниже 0.0.
    worst = evaluate_entry(
        _inp(risk_score=30, liquidity_usd=5000.0, holder_count=0,
             price_change_m5=-99.0, price_change_h1=-99.0,
             buys_m5=0, sells_m5=100, vol_h1=0.0),
        s,
    )
    for d in (best, worst):
        assert d.passed
        assert 0.0 <= d.confidence <= 1.0
    assert best.confidence == 1.0


def test_weights_are_configurable():
    s = _s()
    original = s.signal_conf_w_mom_h1
    try:
        base = evaluate_entry(_inp(price_change_h1=40.0), s).confidence
        s.signal_conf_w_mom_h1 = 0.0  # обнулили вес → вклад h1 исчезает
        off = evaluate_entry(_inp(price_change_h1=40.0), s).confidence
        assert base > off
    finally:
        s.signal_conf_w_mom_h1 = original  # settings кэшируются — восстанавливаем


def test_missing_momentum_data_is_neutral():
    s = _s()
    # Без данных моментума confidence считается как раньше (вклад = 0), в [0,1].
    d = evaluate_entry(_inp(), s)
    assert d.passed
    assert 0.0 < d.confidence <= 1.0
