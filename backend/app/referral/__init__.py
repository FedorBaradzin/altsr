"""Реферальная программа: ставки (чистая логика) + сервис (БД-операции)."""
from __future__ import annotations

from .rate import (
    AUTO_MAX_RATE,
    OVERRIDE_MAX_RATE,
    OVERRIDE_MIN_RATE,
    auto_rate,
    clamp_override,
    effective_rate,
    tier_name,
)

__all__ = [
    "AUTO_MAX_RATE",
    "OVERRIDE_MAX_RATE",
    "OVERRIDE_MIN_RATE",
    "auto_rate",
    "clamp_override",
    "effective_rate",
    "tier_name",
]
