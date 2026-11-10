"""Движок решений стратегии (ТЗ §5).

decide() превращает кандидата (снимок рынка + основание входа) в запись решения,
прогоняя сформированный вход через Risk Engine. Движок детерминирован и не
обращается к сети/БД: при одинаковых входах — одинаковый StrategyDecision.

Порядок:
  1. Торгует ли стратегия в текущем состоянии (CANDIDATE/ACTIVE) — иначе SKIP.
  2. Достаточно ли уверенности сигнала (min_confidence) — иначе SKIP.
  3. Сформировать вход и план выхода, прогнать через Risk Engine.
  4. ENTER при ALLOW, REJECTED при BLOCK (решение сохраняется в обоих случаях).
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from ..risk.delegation import DelegationPolicy, SpendState
from ..risk.engine import evaluate
from ..risk.killswitch import KillSwitchState
from ..risk.policy import RiskPolicy
from ..risk.types import PortfolioState, TradeIntent
from .types import (
    EntryRationale,
    MarketSnapshot,
    StrategyDecision,
    StrategyDefinition,
)


def decide(
    definition: StrategyDefinition,
    snapshot: MarketSnapshot,
    rationale: EntryRationale,
    policy: RiskPolicy,
    portfolio: PortfolioState,
    *,
    recipient: str,
    safety_verdict: str | None = None,
    quote_age_seconds: float | None = None,
    expected_slippage_pct: float | None = None,
    killswitch: KillSwitchState | None = None,
    delegation: DelegationPolicy | None = None,
    spent: SpendState | None = None,
    now: datetime | None = None,
) -> StrategyDecision:
    now = now or datetime.now(timezone.utc)
    version = definition.current_version

    # 1. Состояние жизненного цикла: торгуют только CANDIDATE/ACTIVE.
    if not definition.can_trade:
        return _skip(definition, snapshot, rationale, now,
                     f"стратегия в состоянии {definition.state}")

    # 2. Порог уверенности сигнала.
    if rationale.confidence < version.min_confidence:
        return _skip(definition, snapshot, rationale, now,
                     f"уверенность {rationale.confidence:.2f} < "
                     f"{version.min_confidence:.2f}")

    # 3. Формируем вход и план выхода.
    intent = TradeIntent(
        side="BUY",
        token_key=snapshot.token_key,
        chain=snapshot.chain,
        token_address=snapshot.token_address,
        notional_usd=version.notional_usd,
        recipient=recipient,
        safety_verdict=safety_verdict,  # type: ignore[arg-type]
        quote_age_seconds=quote_age_seconds,
        expected_slippage_pct=expected_slippage_pct,
        liquidity_usd=snapshot.liquidity_usd,
        strategy=definition.key,
        is_exit=False,
    )

    # Устаревший снимок рынка → fail-closed наравне с портфелем (ТЗ §6).
    effective_portfolio = portfolio
    if not snapshot.data_fresh and portfolio.data_fresh:
        effective_portfolio = replace(portfolio, data_fresh=False)

    risk = evaluate(
        intent, policy, effective_portfolio,
        killswitch=killswitch, delegation=delegation, spent=spent, now=now,
    )

    # 4. Итог: ENTER при ALLOW, REJECTED при BLOCK.
    reasons = tuple(rationale.reasons)
    if risk.blocked:
        reasons = reasons + tuple(r.message for r in risk.reasons)

    return StrategyDecision(
        strategy_key=definition.key,
        version=version.version,
        state=definition.state,
        action="ENTER" if risk.allowed else "REJECTED",
        snapshot=snapshot,
        rationale=rationale,
        decided_at=now,
        intent=intent,
        exit_plan=version.exit_plan,
        risk_decision=risk,
        reasons=reasons,
    )


def _skip(
    definition: StrategyDefinition,
    snapshot: MarketSnapshot,
    rationale: EntryRationale,
    now: datetime,
    reason: str,
) -> StrategyDecision:
    return StrategyDecision(
        strategy_key=definition.key,
        version=definition.current_version.version,
        state=definition.state,
        action="SKIP",
        snapshot=snapshot,
        rationale=rationale,
        decided_at=now,
        skip_reason=reason,
        reasons=(reason,),
    )
