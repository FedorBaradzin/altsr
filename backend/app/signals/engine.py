"""Движок входа: ворота (fail-fast) → BUY с причиной и уверенностью.

Чистая логика, без БД/сети — полностью тестируется.
Порядок ворот (из research): safety PASS → risk → ликвидность → возраст → холдеры.
Любое непрохождение → passed=False с причиной отказа.

ВАЖНО: сигнал — это «прошёл фильтры скрининга», а не «вырастет». Не инвест-рекомендация.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..config import Settings
from . import calibration, indicators
from .calibration import Weights


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
    # Ряды свечей для индикаторов (T1). Приходят из OHLCV-источника; None = нет данных.
    closes: list[float] | None = None
    highs: list[float] | None = None
    lows: list[float] | None = None
    # Предыдущий срез объёма h1 — для проверки «объём растёт».
    vol_h1_prev: float | None = None


@dataclass
class SignalDecision:
    passed: bool
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)
    rejected: str | None = None


def evaluate_entry(
    inp: SignalInput, s: Settings, *, weights: Weights | None = None
) -> SignalDecision:
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

    # 7. Технические индикаторы (T1) — ROC/объём/давление/Aroon/ATR, гейт AND.
    if s.indicators_enabled:
        rejected = _indicator_checks(inp, s, reasons)
        if rejected is not None:
            return rejected

    return SignalDecision(True, confidence=_confidence(inp, s, weights), reasons=reasons)


def _indicator_checks(
    inp: SignalInput, s: Settings, reasons: list[str]
) -> SignalDecision | None:
    """Гейт индикаторов (T1). Каждая проверка применяется при наличии данных;
    при отсутствии — отказ, если indicators_require_data, иначе пропуск.
    Возвращает отклоняющее решение или None (прошёл).
    """
    require = s.indicators_require_data

    def _no_data(what: str) -> SignalDecision | None:
        if require:
            return SignalDecision(False, rejected=f"нет данных индикатора: {what}")
        return None

    # ROC по закрытиям.
    if inp.closes is not None and len(inp.closes) >= s.indicator_roc_period + 1:
        val = indicators.roc(inp.closes, s.indicator_roc_period)
        if val < s.indicator_roc_min:
            return SignalDecision(
                False, rejected=f"ROC {val:+.2f}% < {s.indicator_roc_min:+.2f}%")
        reasons.append(f"ROC {val:+.2f}%")
    else:
        r = _no_data("ряд цен (ROC)")
        if r is not None:
            return r

    # Объём h1 растёт.
    if s.indicator_require_vol_rising:
        if inp.vol_h1 is not None and inp.vol_h1_prev is not None:
            if inp.vol_h1 <= inp.vol_h1_prev:
                return SignalDecision(
                    False,
                    rejected=f"объём h1 не растёт (${inp.vol_h1:,.0f} ≤ "
                             f"${inp.vol_h1_prev:,.0f})")
            reasons.append("объём h1 растёт")
        else:
            r = _no_data("срезы объёма h1")
            if r is not None:
                return r

    # Давление покупок (при достаточном числе сделок).
    if inp.buys_m5 is not None and inp.sells_m5 is not None:
        if (inp.buys_m5 + inp.sells_m5) >= 5:
            ratio = inp.buys_m5 / max(1, inp.sells_m5)
            if ratio < s.indicator_buy_sell_min:
                return SignalDecision(
                    False, rejected=f"buys/sells {ratio:.2f} < {s.indicator_buy_sell_min:.2f}")
            reasons.append(f"buys/sells {ratio:.2f}")
    else:
        r = _no_data("txns m5 buys/sells")
        if r is not None:
            return r

    # Aroon-осциллятор (сила/направление тренда).
    if (inp.highs is not None and inp.lows is not None
            and len(inp.highs) >= s.indicator_aroon_period + 1):
        osc = indicators.aroon_osc(inp.highs, inp.lows, s.indicator_aroon_period)
        if osc < s.indicator_aroon_osc_min:
            return SignalDecision(
                False, rejected=f"aroon_osc {osc:+.0f} < {s.indicator_aroon_osc_min:+.0f}")
        reasons.append(f"aroon_osc {osc:+.0f}")
    else:
        r = _no_data("ряды high/low (Aroon)")
        if r is not None:
            return r

    # ATR-коридор: движение должно перекрывать издержки.
    if (inp.highs is not None and inp.lows is not None and inp.closes is not None
            and len(inp.closes) >= s.indicator_atr_period + 1 and inp.closes[-1] > 0):
        a = indicators.atr(inp.highs, inp.lows, inp.closes, s.indicator_atr_period)
        atr_pct = a / inp.closes[-1] * 100.0
        if atr_pct < s.indicator_cost_floor_pct:
            return SignalDecision(
                False,
                rejected=f"ATR {atr_pct:.2f}% < издержки {s.indicator_cost_floor_pct:.2f}%")
        reasons.append(f"ATR {atr_pct:.2f}%")
    else:
        r = _no_data("ряды свечей (ATR)")
        if r is not None:
            return r

    return None


def _confidence(
    inp: SignalInput, s: Settings, weights: Weights | None = None
) -> float:
    # T3: обученные веса (при включённой калибровке и наличии весов) вместо эвристики.
    if s.calibration_enabled and weights is not None:
        feats = calibration.extract_features(
            roc_m5=inp.price_change_m5, roc_h1=inp.price_change_h1,
            buys_m5=inp.buys_m5, sells_m5=inp.sells_m5,
            liquidity_usd=inp.liquidity_usd, risk_score=inp.risk_score,
            vol_h1=inp.vol_h1,
        )
        return round(calibration.predict_proba(feats, weights), 3)
    return _heuristic_confidence(inp, s)


def _heuristic_confidence(inp: SignalInput, s: Settings) -> float:
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
    # Моментум усиливает уверенность: сильный рост h1 + перевес покупок.
    if inp.price_change_h1 is not None:
        c += 0.15 * min(1.0, max(0.0, inp.price_change_h1 / 50.0))
    if inp.buys_m5 is not None and inp.sells_m5 is not None:
        ratio = inp.buys_m5 / max(1, inp.sells_m5)
        if ratio >= 1.5:
            c += 0.08
    return round(min(1.0, max(0.0, c)), 3)
