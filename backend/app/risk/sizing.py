"""Позиционный сайзинг по conviction (T7, рычаг ⑥). Чистая логика, без сети/БД.

Размер входа растёт с уверенностью сигнала (Kelly-подобно), но жёстко ограничен долей
капитала (max_pos_pct) и потолком сессии (budget_cap). Пограничные сигналы получают
меньше, уверенные — больше. Монотонно по confidence.

Honest: больший размер при высокой уверенности не повышает вероятность исхода —
только масштаб ставки. Риск на сделку всё равно ограничен кэпами.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import Settings


@dataclass(frozen=True)
class SizingConfig:
    """Параметры сайзинга.

    min_confidence — ниже порога вход не открывается (размер 0);
    min_pos_pct — доля капитала на пороговой уверенности;
    max_pos_pct — доля капитала на максимальной уверенности (жёсткий кэп на сделку).
    """

    min_confidence: float = 0.5
    min_pos_pct: float = 0.002   # 0.2% equity
    max_pos_pct: float = 0.01    # 1% equity

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_pos_pct <= self.max_pos_pct:
            raise ValueError("нужно 0 ≤ min_pos_pct ≤ max_pos_pct")
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("min_confidence в [0, 1]")


def size_fraction(confidence: float, cfg: SizingConfig) -> float:
    """Доля капитала под вход: 0 ниже порога, линейно от min_pos_pct до max_pos_pct."""
    if confidence < cfg.min_confidence:
        return 0.0
    span = 1.0 - cfg.min_confidence
    if span <= 0:
        return cfg.max_pos_pct
    t = min(1.0, max(0.0, (confidence - cfg.min_confidence) / span))
    return cfg.min_pos_pct + t * (cfg.max_pos_pct - cfg.min_pos_pct)


def position_size_usd(
    confidence: float,
    equity_usd: float,
    cfg: SizingConfig,
    *,
    deployed_usd: float = 0.0,
    budget_cap_usd: float = 0.0,
) -> float:
    """Размер входа в USD с учётом кэпа на сделку и потолка сессии (budget_cap).

    Возвращает 0, если вход не положен (низкая уверенность / нет места под budget_cap).
    """
    if equity_usd <= 0:
        return 0.0
    size = size_fraction(confidence, cfg) * equity_usd
    if budget_cap_usd > 0:
        room = max(0.0, budget_cap_usd - deployed_usd)
        size = min(size, room)
    return max(0.0, size)


def kelly_fraction(
    win_prob: float, payoff_ratio: float, *, kelly_multiplier: float = 0.5
) -> float:
    """Доля банка по Келли (дробная, по умолчанию half-Kelly), отсечённая снизу нулём.

    win_prob — вероятность выигрыша p; payoff_ratio — отношение выигрыша к проигрышу b.
    f* = (p*(b+1) - 1) / b, затем умножается на kelly_multiplier. Отрицательная → 0.
    """
    if payoff_ratio <= 0:
        return 0.0
    f = (win_prob * (payoff_ratio + 1) - 1) / payoff_ratio
    return max(0.0, f * kelly_multiplier)


def sizing_config_from_settings(s: Settings) -> SizingConfig:
    return SizingConfig(
        min_confidence=s.sizing_min_confidence,
        min_pos_pct=s.sizing_min_pos_pct,
        max_pos_pct=s.sizing_max_pos_pct,
    )
