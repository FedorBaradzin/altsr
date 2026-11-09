"""Цепочка выходов по приоритету (чистая логика, без БД/сети).

Порядок (из research-дока): hard stop-loss → trailing stop (от пика, после арминга) →
take-profit (частичный) → stall → time. Первый сработавший — действие.

«Выход при малейшем падении» реализован как trailing от пика с армингом: тугой trailing
включается только после выхода в плюс на arm_after_profit_pct, иначе вход-проскальзывание
выбивало бы позицию мгновенно. Это сохраняет намерение, но не сжигает депозит на шуме.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExitConfig:
    hard_stop_pct: float
    arm_after_profit_pct: float
    trailing_stop_pct: float
    tp_x: float
    tp_fraction: float
    stall_minutes: int
    max_hold_minutes: int


@dataclass
class PositionState:
    entry_price: float
    peak_price: float
    price: float
    minutes_since_open: float
    minutes_since_high: float
    tp_taken: bool


@dataclass
class ExitAction:
    kind: str            # hold | partial | close
    reason: str = ""
    fraction: float = 0.0  # для partial — доля первоначальной позиции


def evaluate_exit(st: PositionState, cfg: ExitConfig) -> ExitAction:
    entry, peak, price = st.entry_price, st.peak_price, st.price

    # 1. Hard stop-loss
    if price <= entry * (1 - cfg.hard_stop_pct):
        return ExitAction("close", f"hard stop −{cfg.hard_stop_pct*100:.0f}%")

    # 2. Trailing stop (только после арминга: пик дошёл до +arm%)
    armed = peak >= entry * (1 + cfg.arm_after_profit_pct)
    if armed and price <= peak * (1 - cfg.trailing_stop_pct):
        return ExitAction("close", f"trailing −{cfg.trailing_stop_pct*100:.0f}% от пика")

    # 3. Take-profit (частичный, один раз)
    if not st.tp_taken and cfg.tp_fraction > 0 and price >= entry * cfg.tp_x:
        if cfg.tp_fraction >= 1.0:
            return ExitAction("close", f"take-profit {cfg.tp_x:g}x")
        return ExitAction("partial", f"take-profit {cfg.tp_x:g}x (частично)",
                          fraction=cfg.tp_fraction)

    # 4. Stall — нет нового хая N минут
    if st.minutes_since_high >= cfg.stall_minutes:
        return ExitAction("close", f"stall: нет хая {cfg.stall_minutes}м")

    # 5. Max hold
    if st.minutes_since_open >= cfg.max_hold_minutes:
        return ExitAction("close", f"time exit {cfg.max_hold_minutes}м")

    return ExitAction("hold")


def build_plan(cfg: ExitConfig) -> list[str]:
    """Прозрачный план выхода (НЕ прогноз прибыли) — что бот сделает с позицией."""
    return [
        f"Жёсткий стоп: −{cfg.hard_stop_pct*100:.0f}% от входа",
        f"Фиксация прибыли: {int(cfg.tp_fraction*100)}% на {cfg.tp_x:g}x",
        f"Trailing: −{cfg.trailing_stop_pct*100:.0f}% от пика "
        f"(после +{cfg.arm_after_profit_pct*100:.0f}%)",
        f"Выход по застою: нет нового хая {cfg.stall_minutes} мин",
        f"Макс. удержание: {cfg.max_hold_minutes} мин",
    ]
