"""Версионированная risk-policy (ТЗ §6, §9).

Политики версионируются: изменение политики НЕ меняет задним числом исторические
решения. В решении сохраняется version использованной политики.

Значения по умолчанию — НАЧАЛЬНЫЕ ТЕСТОВЫЕ параметры из ТЗ, НЕ рекомендованные для
реальной торговли. На неликвидных токенах фактический убыток может сильно превышать
заданный стоп.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RiskPolicy:
    version: str
    max_position_pct: float          # доля equity на одну позицию (0.01 = 1%)
    max_exposure_pct: float          # совокупная экспозиция (0.20 = 20%)
    daily_loss_limit_pct: float      # дневной лимит убытка (0.02 = 2%)
    max_open_positions: int
    max_slippage_pct: float          # 0.01 = 1%
    min_liquidity_usd: float
    max_quote_age_seconds: float     # TTL котировки
    allowed_safety_verdicts: tuple[str, ...] = field(default=("PASS",))
    block_on_stale_data: bool = True


# Начальные тестовые значения (ТЗ §6). ТОЛЬКО для paper/симуляции.
DEFAULT_POLICY = RiskPolicy(
    version="paper-defaults-v1",
    max_position_pct=0.01,
    max_exposure_pct=0.20,
    daily_loss_limit_pct=0.02,
    max_open_positions=5,
    max_slippage_pct=0.01,
    min_liquidity_usd=10_000.0,
    max_quote_age_seconds=30.0,
    allowed_safety_verdicts=("PASS",),
    block_on_stale_data=True,
)
