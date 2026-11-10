"""Hard-rules R1–R6 (T4, видео 70/71): fail-fast гейты входа с rule_id.

Чистая логика, без сети/БД. Порядок важен — первая сработавшая блокирует, её rule_id
и причина доступны для алертов. R6 (соц-сигналы) — не блок, а только буст confidence,
поэтому возвращается отдельно и не участвует в fail-fast.

Пороги — из конфига (консервативные дефолты-примеры, не рекомендация).
Принцип: «нет данных ≠ безопасно». Неизвестная верификация/объём → блок при включении.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HardRuleInput:
    """Факты для R1–R6 на момент входа. None = нет данных."""

    volume_usd: float | None = None
    contract_verified: bool | None = None
    buys_m5: int | None = None
    sells_m5: int | None = None
    dev_pct: float | None = None       # доля dev/insiders, %
    has_bundles: bool = False          # bundle-закупка (из safety/GoPlus)
    repeat_rug: bool = False           # создатель замечен в прошлых rug
    consec_losses: int = 0             # подряд убытков на инстанс/сессию
    social_score: float | None = None  # внешний соц-сигнал (X), только для R6


@dataclass(frozen=True)
class HardRuleResult:
    """Итог fail-fast проверки. rule_id/reason заданы при блокировке."""

    blocked: bool
    rule_id: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class HardRuleConfig:
    min_volume_usd: float = 0.0
    require_verified: bool = False
    sell_buy_max: float = 2.0
    dev_max_pct: float = 10.0
    max_consec_losses: int = 2


def _r1_volume(i: HardRuleInput, c: HardRuleConfig) -> HardRuleResult | None:
    if c.min_volume_usd <= 0:
        return None
    if i.volume_usd is None:
        return HardRuleResult(True, "R1", "нет данных об объёме")
    if i.volume_usd < c.min_volume_usd:
        return HardRuleResult(
            True, "R1", f"объём ${i.volume_usd:,.0f} < ${c.min_volume_usd:,.0f}")
    return None


def _r2_verified(i: HardRuleInput, c: HardRuleConfig) -> HardRuleResult | None:
    if not c.require_verified:
        return None
    if not i.contract_verified:  # False или None → не верифицирован
        return HardRuleResult(True, "R2", "контракт не верифицирован")
    return None


def _r3_sell_pressure(i: HardRuleInput, c: HardRuleConfig) -> HardRuleResult | None:
    if i.buys_m5 is None or i.sells_m5 is None:
        return None
    if (i.buys_m5 + i.sells_m5) < 5:   # мало сделок — не судим
        return None
    ratio = i.sells_m5 / max(1, i.buys_m5)
    if ratio >= c.sell_buy_max:
        return HardRuleResult(
            True, "R3", f"sells/buys {ratio:.2f} ≥ {c.sell_buy_max:.2f}")
    return None


def _r4_dev_insiders(i: HardRuleInput, c: HardRuleConfig) -> HardRuleResult | None:
    if i.repeat_rug:
        return HardRuleResult(True, "R4", "создатель замечен в прошлых rug")
    if i.has_bundles:
        return HardRuleResult(True, "R4", "bundle-закупка")
    if i.dev_pct is not None and i.dev_pct >= c.dev_max_pct:
        return HardRuleResult(
            True, "R4", f"dev/insiders {i.dev_pct:.1f}% ≥ {c.dev_max_pct:.1f}%")
    return None


def _r5_consec_losses(i: HardRuleInput, c: HardRuleConfig) -> HardRuleResult | None:
    if c.max_consec_losses > 0 and i.consec_losses >= c.max_consec_losses:
        return HardRuleResult(
            True, "R5", f"{i.consec_losses} убытков подряд ≥ {c.max_consec_losses}")
    return None


# Порядок fail-fast: дешёвые и строгие — раньше.
_RULES = (_r1_volume, _r2_verified, _r3_sell_pressure, _r4_dev_insiders, _r5_consec_losses)


def check_hard_rules(i: HardRuleInput, c: HardRuleConfig) -> HardRuleResult:
    """Прогоняет R1–R5 по порядку; первая блокирующая — результат. R6 отдельно."""
    for rule in _RULES:
        res = rule(i, c)
        if res is not None:
            return res
    return HardRuleResult(False)


def social_confidence_boost(i: HardRuleInput, *, max_boost: float = 0.1) -> float:
    """R6: соц-сигнал только усиливает confidence (0..max_boost), не триггерит вход."""
    if i.social_score is None:
        return 0.0
    return max(0.0, min(max_boost, max_boost * i.social_score))
