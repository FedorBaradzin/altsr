"""Позиционный сайзинг по conviction (T7): монотонность, кэп, budget_cap."""
from __future__ import annotations

import pytest

from app.risk.sizing import (
    SizingConfig,
    kelly_fraction,
    position_size_usd,
    size_fraction,
)

EQUITY = 100_000.0


def _cfg(**over) -> SizingConfig:
    base = dict(min_confidence=0.5, min_pos_pct=0.002, max_pos_pct=0.01)
    base.update(over)
    return SizingConfig(**base)


def test_below_threshold_is_zero():
    assert size_fraction(0.4, _cfg()) == 0.0
    assert position_size_usd(0.4, EQUITY, _cfg()) == 0.0


def test_monotonic_in_confidence():
    cfg = _cfg()
    sizes = [position_size_usd(c, EQUITY, cfg) for c in (0.5, 0.6, 0.75, 0.9, 1.0)]
    assert sizes == sorted(sizes)              # не убывает
    assert sizes[0] < sizes[-1]                # и реально растёт


def test_cap_respected():
    # На максимальной уверенности размер = max_pos_pct * equity, не больше.
    size = position_size_usd(1.0, EQUITY, _cfg())
    assert size == pytest.approx(0.01 * EQUITY)
    assert size / EQUITY <= _cfg().max_pos_pct + 1e-9


def test_budget_cap_limits_size():
    # Под budget_cap осталось всего $300 → размер урезан до него.
    size = position_size_usd(1.0, EQUITY, _cfg(),
                             deployed_usd=9_700.0, budget_cap_usd=10_000.0)
    assert size == pytest.approx(300.0)


def test_budget_cap_full_blocks():
    size = position_size_usd(1.0, EQUITY, _cfg(),
                             deployed_usd=10_000.0, budget_cap_usd=10_000.0)
    assert size == 0.0


def test_zero_equity_zero_size():
    assert position_size_usd(1.0, 0.0, _cfg()) == 0.0


def test_config_validation():
    with pytest.raises(ValueError):
        SizingConfig(min_pos_pct=0.05, max_pos_pct=0.01)   # min > max


def test_kelly_fraction_basic():
    # p=0.6, b=1 → f*=(0.6*2-1)/1=0.2; half-Kelly → 0.1.
    assert kelly_fraction(0.6, 1.0, kelly_multiplier=0.5) == pytest.approx(0.1)
    # Невыгодно (p низкий) → отсечка нулём.
    assert kelly_fraction(0.3, 1.0) == 0.0
    assert kelly_fraction(0.6, 0.0) == 0.0   # нет пэйоффа
