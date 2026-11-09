"""Цепочка выходов: приоритеты hard stop / trailing / TP / stall / time."""
from __future__ import annotations

from app.paper.exits import ExitConfig, PositionState, build_plan, evaluate_exit

CFG = ExitConfig(
    hard_stop_pct=0.25, arm_after_profit_pct=0.20, trailing_stop_pct=0.08,
    tp_x=2.0, tp_fraction=0.5, stall_minutes=15, max_hold_minutes=240,
)


def _st(**kw):
    base = dict(entry_price=1.0, peak_price=1.0, price=1.0,
                minutes_since_open=1.0, minutes_since_high=1.0, tp_taken=False)
    base.update(kw)
    return PositionState(**base)


def test_hold_when_flat():
    assert evaluate_exit(_st(), CFG).kind == "hold"


def test_hard_stop():
    a = evaluate_exit(_st(price=0.70), CFG)  # ≤ 0.75
    assert a.kind == "close" and "hard stop" in a.reason


def test_trailing_requires_arm():
    # Пик 1.10 (<1.20 — не армлено): просадка не триггерит trailing.
    assert evaluate_exit(_st(peak_price=1.10, price=1.00), CFG).kind == "hold"
    # Пик 1.50 (армлено), цена 1.35 ≤ 1.50*0.92=1.38 → trailing close.
    a = evaluate_exit(_st(peak_price=1.50, price=1.35), CFG)
    assert a.kind == "close" and "trailing" in a.reason


def test_take_profit_partial():
    a = evaluate_exit(_st(peak_price=2.1, price=2.1), CFG)
    assert a.kind == "partial" and a.fraction == 0.5


def test_take_profit_full_when_fraction_1():
    cfg = ExitConfig(**{**CFG.__dict__, "tp_fraction": 1.0})
    a = evaluate_exit(_st(peak_price=2.1, price=2.1), cfg)
    assert a.kind == "close"


def test_stall_close():
    a = evaluate_exit(_st(minutes_since_high=20), CFG)
    assert a.kind == "close" and "stall" in a.reason


def test_time_exit():
    a = evaluate_exit(_st(minutes_since_open=300, minutes_since_high=1), CFG)
    assert a.kind == "close" and "time" in a.reason


def test_hard_stop_beats_everything():
    # Даже если время вышло — hard stop приоритетнее по порядку (оба close, но hard первый).
    a = evaluate_exit(_st(price=0.5, minutes_since_open=300), CFG)
    assert "hard stop" in a.reason


def test_plan_has_five_lines():
    plan = build_plan(CFG)
    assert len(plan) == 5
    assert any("стоп" in p.lower() for p in plan)
