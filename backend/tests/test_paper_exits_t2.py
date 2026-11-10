"""T2 — тренд ликвидности + верхние приоритеты цепочки выходов.

Проверяем: обвал ликвидности → немедленный выход; kill-switch/session-stop и
критическое изменение безопасности выше hard-stop; trailing от пика, а не от входа.
"""
from __future__ import annotations

from app.paper.exits import (
    ExitConfig,
    PositionState,
    SafetySnap,
    detect_safety_regression,
    evaluate_exit,
    liquidity_dropped,
)


def _cfg(**over) -> ExitConfig:
    base = dict(hard_stop_pct=0.25, arm_after_profit_pct=0.20, trailing_stop_pct=0.08,
                tp_x=2.0, tp_fraction=0.5, stall_minutes=15, max_hold_minutes=240,
                liq_drop_pct=0.15)
    base.update(over)
    return ExitConfig(**base)


def _pos(**over) -> PositionState:
    base = dict(entry_price=1.0, peak_price=1.0, price=1.0,
                minutes_since_open=1.0, minutes_since_high=0.0, tp_taken=False)
    base.update(over)
    return PositionState(**base)


# --- liquidity_dropped helper ---

def test_liquidity_dropped_detects_collapse():
    assert liquidity_dropped(100_000, 50_000, 0.15) is True   # −50%
    assert liquidity_dropped(100_000, 90_000, 0.15) is False  # −10%
    assert liquidity_dropped(None, 50_000, 0.15) is False     # нет данных
    assert liquidity_dropped(100_000, None, 0.15) is False
    assert liquidity_dropped(0, 0, 0.15) is False


def test_liquidity_collapse_forces_immediate_exit():
    # Цена в плюсе, но ликвидность обвалилась → выходим немедленно.
    st = _pos(price=1.5, peak_price=1.5,
              liquidity_prev_usd=100_000, liquidity_usd=40_000)
    act = evaluate_exit(st, _cfg())
    assert act.kind == "close"
    assert "ликвидность" in act.reason


# --- верхние приоритеты ---

def test_kill_switch_beats_everything():
    # Даже при цене в хорошем плюсе — kill-switch закрывает.
    st = _pos(price=3.0, peak_price=3.0, kill_switch=True)
    act = evaluate_exit(st, _cfg())
    assert act.kind == "close" and "kill-switch" in act.reason


def test_session_stop_closes():
    st = _pos(price=1.1, peak_price=1.1, session_stopped=True)
    assert evaluate_exit(st, _cfg()).reason.startswith("session-stop")


def test_safety_regression_beats_hard_stop():
    # Цена ещё не достигла hard-stop, но безопасность критически ухудшилась.
    st = _pos(price=0.9, safety_regression="LP разблокирован/вытащен")
    act = evaluate_exit(st, _cfg())
    assert act.kind == "close" and "безопасность" in act.reason


# --- детекция регресса безопасности ---

def test_detect_safety_regression_cases():
    locked = SafetySnap(lp_locked=True, mint_authority_active=False, sell_tax_pct=2.0)
    assert detect_safety_regression(locked, locked) is None
    # LP вытащили
    assert "LP" in detect_safety_regression(
        locked, SafetySnap(lp_locked=False, mint_authority_active=False, sell_tax_pct=2.0))
    # authority вернули
    assert "authority" in detect_safety_regression(
        locked, SafetySnap(lp_locked=True, mint_authority_active=True, sell_tax_pct=2.0))
    # налог вырос
    assert "налог" in detect_safety_regression(
        locked, SafetySnap(lp_locked=True, mint_authority_active=False, sell_tax_pct=10.0),
        tax_jump_pct=5.0)


# --- trailing: от пика, не от входа (DoD T2) ---

def test_trailing_does_not_fire_at_entry_noise():
    # Небольшой минус сразу после входа (пик не дошёл до +arm%) — НЕ выходим.
    st = _pos(entry_price=1.0, peak_price=1.02, price=0.97)
    assert evaluate_exit(st, _cfg()).kind == "hold"


def test_trailing_fires_from_peak_after_arming():
    # Пик дошёл до +25% (>arm 20%), затем откат −8% от пика → выход.
    st = _pos(entry_price=1.0, peak_price=1.25, price=1.25 * 0.91)
    act = evaluate_exit(st, _cfg())
    assert act.kind == "close" and "trailing" in act.reason
