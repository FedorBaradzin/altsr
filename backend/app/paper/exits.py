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
    # T2: доля падения ликвидности между срезами, после которой — немедленный выход.
    liq_drop_pct: float = 0.15


@dataclass
class PositionState:
    entry_price: float
    peak_price: float
    price: float
    minutes_since_open: float
    minutes_since_high: float
    tp_taken: bool
    # --- T2: аварийные верхнеприоритетные сигналы (всё опционально) ---
    kill_switch: bool = False          # глобальная аварийная остановка
    session_stopped: bool = False      # session-stop (лимит сессии достигнут)
    safety_regression: str | None = None  # причина критического изменения безопасности
    liquidity_usd: float | None = None
    liquidity_prev_usd: float | None = None


@dataclass
class SafetySnap:
    """Минимальный снимок безопасности для детекции регресса (T2)."""

    lp_locked: bool = False
    mint_authority_active: bool = False
    sell_tax_pct: float = 0.0


def detect_safety_regression(
    before: SafetySnap, after: SafetySnap, *, tax_jump_pct: float = 5.0
) -> str | None:
    """Критическое ухудшение безопасности открытой позиции → причина или None."""
    if before.lp_locked and not after.lp_locked:
        return "LP разблокирован/вытащен"
    if not before.mint_authority_active and after.mint_authority_active:
        return "вернули mint authority"
    if after.sell_tax_pct - before.sell_tax_pct >= tax_jump_pct:
        return (f"налог на продажу вырос "
                f"{before.sell_tax_pct:.0f}%→{after.sell_tax_pct:.0f}%")
    return None


def liquidity_dropped(prev_usd: float | None, now_usd: float | None, pct: float) -> bool:
    """True, если ликвидность упала больше чем на pct между срезами.

    Нет данных (None) трактуется как отсутствие сигнала (решают другие гейты),
    но нулевая/отрицательная текущая ликвидность при положительной прошлой — обвал.
    """
    if prev_usd is None or now_usd is None:
        return False
    if prev_usd <= 0:
        return False
    return (prev_usd - now_usd) / prev_usd > pct


@dataclass
class ExitAction:
    kind: str            # hold | partial | close
    reason: str = ""
    fraction: float = 0.0  # для partial — доля первоначальной позиции


def evaluate_exit(st: PositionState, cfg: ExitConfig) -> ExitAction:
    """Цепочка выходов по приоритету (T2). Первый сработавший — действие.

    Порядок: ① kill-switch/session-stop → ② критическое изменение безопасности →
    ③ обвал ликвидности → ④ hard-stop → ⑤ trailing → ⑥ partial TP → ⑦ stall/time.
    Сигнал стратегии (⑦ в ТЗ) приходит извне, здесь не оценивается.
    """
    entry, peak, price = st.entry_price, st.peak_price, st.price

    # ① Аварийная остановка / session-stop — безусловный выход.
    if st.kill_switch:
        return ExitAction("close", "kill-switch — аварийный выход")
    if st.session_stopped:
        return ExitAction("close", "session-stop — закрытие позиций")

    # ② Критическое изменение безопасности (LP/authority/налог).
    if st.safety_regression:
        return ExitAction("close", f"безопасность: {st.safety_regression}")

    # ③ Обвал ликвидности между срезами.
    if liquidity_dropped(st.liquidity_prev_usd, st.liquidity_usd, cfg.liq_drop_pct):
        return ExitAction("close", f"ликвидность упала >{cfg.liq_drop_pct*100:.0f}%")

    # ④ Hard stop-loss
    if price <= entry * (1 - cfg.hard_stop_pct):
        return ExitAction("close", f"hard stop −{cfg.hard_stop_pct*100:.0f}%")

    # ⑤ Trailing stop (только после арминга: пик дошёл до +arm%)
    armed = peak >= entry * (1 + cfg.arm_after_profit_pct)
    if armed and price <= peak * (1 - cfg.trailing_stop_pct):
        return ExitAction("close", f"trailing −{cfg.trailing_stop_pct*100:.0f}% от пика")

    # ⑥ Take-profit (частичный, один раз)
    if not st.tp_taken and cfg.tp_fraction > 0 and price >= entry * cfg.tp_x:
        if cfg.tp_fraction >= 1.0:
            return ExitAction("close", f"take-profit {cfg.tp_x:g}x")
        return ExitAction("partial", f"take-profit {cfg.tp_x:g}x (частично)",
                          fraction=cfg.tp_fraction)

    # ⑦ Stall — нет нового хая N минут
    if st.minutes_since_high >= cfg.stall_minutes:
        return ExitAction("close", f"stall: нет хая {cfg.stall_minutes}м")

    # Max hold
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
