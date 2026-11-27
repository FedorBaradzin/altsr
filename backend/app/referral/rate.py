"""Ставки реферальной программы (чистая логика, без БД — юнит-тестируется).

Авто-ставка по числу АКТИВНЫХ рефералов (у каждого ≥1 оплаченный платёж):
    Starter 1–4   → 10%
    Bronze  5–9   → 15%
    Silver  10–24 → 20%
    Gold    25+   → 30%  (авто-потолок)
Выше 30% — ТОЛЬКО через админский override (индивидуальная ставка 30–50%).
"""
from __future__ import annotations

# Авто-потолок: максимум, который даёт автоматическая логика по числу рефералов.
AUTO_MAX_RATE = 0.30
# Границы индивидуального override (админ): 30%–50%.
OVERRIDE_MIN_RATE = 0.30
OVERRIDE_MAX_RATE = 0.50

# Пороги уровней: (минимум активных рефералов, ставка, имя тира).
_TIERS: tuple[tuple[int, float, str], ...] = (
    (25, 0.30, "Gold"),
    (10, 0.20, "Silver"),
    (5, 0.15, "Bronze"),
    (1, 0.10, "Starter"),
)


def auto_rate(active: int) -> float:
    """Авто-ставка (доля 0..0.30) по числу активных рефералов."""
    for threshold, rate, _name in _TIERS:
        if active >= threshold:
            return rate
    return 0.0


def tier_name(active: int, override: float | None = None) -> str:
    """Имя тира для UI. Непустой override → «Individual»."""
    if override is not None:
        return "Individual"
    for threshold, _rate, name in _TIERS:
        if active >= threshold:
            return name
    return "None"


def clamp_override(rate: float) -> float:
    """Привести индивидуальную ставку к допустимому коридору 0.30–0.50."""
    return max(OVERRIDE_MIN_RATE, min(OVERRIDE_MAX_RATE, rate))


def effective_rate(override: float | None, active: int) -> float:
    """Итоговая ставка: override (зажатый в 0.30–0.50), иначе авто-ставка.

    override передаётся как `user.referral_rate_override` (может быть None).
    """
    if override is not None:
        return clamp_override(override)
    return auto_rate(active)
