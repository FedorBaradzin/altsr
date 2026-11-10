"""Движок входа: ворота (fail-fast) → BUY с причиной и уверенностью.

Чистая логика, без БД/сети — полностью тестируется.
Порядок ворот (из research): safety PASS → risk → ликвидность → возраст → холдеры.
Любое непрохождение → passed=False с причиной отказа.

ВАЖНО: сигнал — это «прошёл фильтры скрининга», а не «вырастет». Не инвест-рекомендация.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..config import Settings


@dataclass
class SignalInput:
    chain: str
    address: str
    liquidity_usd: float | None = None
    age_minutes: float | None = None
    holder_count: int | None = None
    verdict: str | None = None
    risk_score: int | None = None
    # Моментум (DexScreener) — вход только в растущие.
    price_change_m5: float | None = None
    price_change_h1: float | None = None
    vol_h1: float | None = None
    vol_h6: float | None = None
    buys_m5: int | None = None
    sells_m5: int | None = None


@dataclass
class SignalDecision:
    passed: bool
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)
    rejected: str | None = None


def evaluate_entry(inp: SignalInput, s: Settings) -> SignalDecision:
    reasons: list[str] = []

    # 1. Safety-вердикт
    if s.signal_require_pass:
        if inp.verdict is None:
            return SignalDecision(False, rejected="нет safety-отчёта")
        if inp.verdict != "PASS":
            return SignalDecision(False, rejected=f"safety-вердикт {inp.verdict}")
        risk_note = f" (risk {inp.risk_score})" if inp.risk_score is not None else ""
        reasons.append("safety PASS" + risk_note)

    # 2. Порог риска
    if inp.risk_score is not None and inp.risk_score > s.signal_max_risk:
        return SignalDecision(False, rejected=f"risk_score {inp.risk_score} > {s.signal_max_risk}")

    # 3. Ликвидность (обязательна и известна)
    if inp.liquidity_usd is None:
        return SignalDecision(False, rejected="нет данных о ликвидности")
    liq, lmin = inp.liquidity_usd, s.signal_min_liquidity_usd
    if liq < lmin:
        return SignalDecision(False, rejected=f"ликвидность ${liq:,.0f} < ${lmin:,.0f}")
    reasons.append(f"ликвидность ${liq:,.0f} ≥ ${lmin:,.0f}")

    # 4. Возраст (если известен)
    if inp.age_minutes is not None:
        if inp.age_minutes < s.signal_min_age_minutes:
            return SignalDecision(False, rejected=f"слишком молодой: {inp.age_minutes:.0f} мин")
        if inp.age_minutes > s.signal_max_age_minutes:
            return SignalDecision(False, rejected=f"слишком старый: {inp.age_minutes:.0f} мин")
        reasons.append(f"возраст {inp.age_minutes:.0f} мин в окне "
                       f"{s.signal_min_age_minutes}–{s.signal_max_age_minutes}")

    # 5. Холдеры (если задан порог)
    if s.signal_min_holders > 0:
        if inp.holder_count is None:
            return SignalDecision(False, rejected="нет данных о холдерах")
        if inp.holder_count < s.signal_min_holders:
            return SignalDecision(
                False, rejected=f"холдеров {inp.holder_count} < {s.signal_min_holders}"
            )
        reasons.append(f"холдеров {inp.holder_count}")
    elif inp.holder_count is not None:
        reasons.append(f"холдеров {inp.holder_count}")

    # 6. Моментум — входим ТОЛЬКО в растущие (DexScreener priceChange + давление покупок)
    if s.momentum_enabled:
        has_mom = inp.price_change_m5 is not None and inp.price_change_h1 is not None
        if not has_mom:
            if s.momentum_require_data:
                return SignalDecision(False, rejected="нет данных моментума")
        else:
            if inp.price_change_m5 <= s.momentum_min_change_m5:
                return SignalDecision(
                    False,
                    rejected=f"m5 {inp.price_change_m5:+.1f}% ≤ {s.momentum_min_change_m5:+.1f}%",
                )
            if inp.price_change_h1 <= s.momentum_min_change_h1:
                return SignalDecision(
                    False,
                    rejected=f"h1 {inp.price_change_h1:+.1f}% ≤ {s.momentum_min_change_h1:+.1f}%",
                )
            if (
                inp.buys_m5 is not None and inp.sells_m5 is not None
                and (inp.buys_m5 + inp.sells_m5) >= 5
            ):
                ratio = inp.buys_m5 / max(1, inp.sells_m5)
                if ratio < s.momentum_min_buy_sell:
                    return SignalDecision(
                        False, rejected=f"buys/sells {ratio:.2f} < {s.momentum_min_buy_sell:.2f}"
                    )
            reasons.append(
                f"моментум m5 {inp.price_change_m5:+.1f}%, h1 {inp.price_change_h1:+.1f}%"
            )

    return SignalDecision(True, confidence=_confidence(inp, s), reasons=reasons)


def _confidence(inp: SignalInput, s: Settings) -> float:
    """Уверенность входа [0..1]: статическая база + рыночная динамика.

    ВАЖНО: динамическая часть (моментум/давление покупок/оборот) повышает
    ОЖИДАЕМУЮ ЦЕННОСТЬ и качество РАНЖИРОВАНИЯ уже прошедших ворота входов —
    это НЕ гарантия прибыли (большинство новых токенов идут в ноль).
    """
    c = 0.5
    # Низкий риск → выше уверенность.
    if inp.risk_score is not None and s.signal_max_risk > 0:
        c += 0.25 * max(0.0, (s.signal_max_risk - inp.risk_score) / s.signal_max_risk)
    # Запас по ликвидности.
    if inp.liquidity_usd is not None and s.signal_min_liquidity_usd > 0:
        c += 0.15 * min(1.0, inp.liquidity_usd / (s.signal_min_liquidity_usd * 4))
    # Достаточно холдеров.
    if inp.holder_count is not None and inp.holder_count >= 100:
        c += 0.10
    # Рыночная динамика: рост m5/h1, давление покупок, оборот к ликвидности.
    c += _momentum_confidence(inp, s)
    return round(min(1.0, max(0.0, c)), 3)


def _momentum_confidence(inp: SignalInput, s: Settings) -> float:
    """Неотрицательный вклад рыночной динамики в уверенность.

    Считается по НАЛИЧИЮ данных моментума, независимо от гейта momentum_enabled:
    гейты решают, входить ли вообще, а этот вклад ранжирует прошедшие входы по
    силе краткосрочного роста и перевеса покупок. Все веса — из Settings.
    """
    bonus = 0.0
    # Краткосрочный рост m5/h1: больше рост → больше вклад (падение = 0).
    if inp.price_change_m5 is not None and s.signal_conf_mom_m5_scale > 0:
        bonus += s.signal_conf_w_mom_m5 * min(
            1.0, max(0.0, inp.price_change_m5 / s.signal_conf_mom_m5_scale)
        )
    if inp.price_change_h1 is not None and s.signal_conf_mom_h1_scale > 0:
        bonus += s.signal_conf_w_mom_h1 * min(
            1.0, max(0.0, inp.price_change_h1 / s.signal_conf_mom_h1_scale)
        )
    # Давление покупок: buys/sells выше опорного (~1.3) → плавно растущий вклад.
    if (
        inp.buys_m5 is not None and inp.sells_m5 is not None
        and (inp.buys_m5 + inp.sells_m5) > 0 and s.signal_conf_buy_sell_ref > 0
    ):
        ratio = inp.buys_m5 / max(1, inp.sells_m5)
        ref = s.signal_conf_buy_sell_ref
        if ratio > ref:
            # Максимум вклада при ratio ≥ 2×ref.
            bonus += s.signal_conf_w_buy_pressure * min(1.0, (ratio - ref) / ref)
    # Здоровый оборот: vol_h1 относительно ликвидности → выше вклад.
    if (
        inp.vol_h1 is not None and inp.liquidity_usd is not None
        and inp.liquidity_usd > 0 and s.signal_conf_vol_liq_ref > 0
    ):
        turnover = inp.vol_h1 / inp.liquidity_usd
        bonus += s.signal_conf_w_volume * min(1.0, turnover / s.signal_conf_vol_liq_ref)
    return bonus
