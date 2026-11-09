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

    return SignalDecision(True, confidence=_confidence(inp, s), reasons=reasons)


def _confidence(inp: SignalInput, s: Settings) -> float:
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
    return round(min(1.0, max(0.0, c)), 3)
