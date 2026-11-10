"""Risk Engine — центральный детерминированный гейт (ТЗ §6).

ЕДИНАЯ точка решения «можно ли исполнить сделку». Независим от AI, стратегии и
маршрутизатора. Чистая функция: одинаковые входы → одинаковое решение.

Принципы:
- fail-closed: нет достоверных данных → отказ во входе;
- аварийная остановка блокирует новые входы; выход — только по безопасному пути и
  только при достоверных котировках (нельзя бесконтрольно продавать без цены);
- собираем ВСЕ причины отказа (а не первую), чтобы вызывающий видел полную картину.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .delegation import DelegationPolicy, SpendState
from .delegation import check as check_delegation
from .killswitch import KillSwitchState
from .policy import RiskPolicy
from .types import PortfolioState, RiskDecision, RiskReason, TradeIntent


def evaluate(
    intent: TradeIntent,
    policy: RiskPolicy,
    portfolio: PortfolioState,
    *,
    killswitch: KillSwitchState | None = None,
    delegation: DelegationPolicy | None = None,
    spent: SpendState | None = None,
    now: datetime | None = None,
) -> RiskDecision:
    now = now or datetime.now(timezone.utc)
    reasons: list[RiskReason] = []

    # --- Аварийная остановка (ТЗ §6, AC-15) ---
    if killswitch is not None and killswitch.active:
        if intent.is_entry:
            reasons.append(RiskReason(
                "emergency_stop",
                f"Аварийная остановка активна ({killswitch.reason}) — новые входы запрещены"))
        # Для выхода остановка сама по себе не запрещает закрытие по безопасному пути;
        # ограничение на выход даёт только потеря достоверных данных (ниже).

    # --- Потеря рыночных данных: fail-closed для входов И выходов (ТЗ §6) ---
    if policy.block_on_stale_data and not portfolio.data_fresh:
        reasons.append(RiskReason(
            "market_data_stale",
            "Потеряны достоверные рыночные данные — операция запрещена (fail-closed)"))

    # --- Гейты нового входа ---
    if intent.is_entry:
        reasons.extend(_entry_checks(intent, policy, portfolio))

    # --- Делегация (вход и выход: получатель/отзыв/срок; расходы — только вход) ---
    if delegation is not None:
        reasons.extend(check_delegation(intent, delegation, spent or SpendState(), now=now))

    verdict = "BLOCK" if reasons else "ALLOW"
    return RiskDecision(
        verdict=verdict,
        reasons=tuple(reasons),
        policy_version=policy.version,
        intent_key=intent.token_key,
        evaluated_at=now,
    )


def _entry_checks(
    intent: TradeIntent, policy: RiskPolicy, portfolio: PortfolioState
) -> list[RiskReason]:
    reasons: list[RiskReason] = []
    equity = portfolio.equity_usd

    # Безопасность (AC-08): во вход допускаем только разрешённые вердикты (по умолчанию PASS).
    if policy.enforce_safety and intent.safety_verdict not in policy.allowed_safety_verdicts:
        reasons.append(RiskReason(
            "safety_not_passed",
            f"Вердикт безопасности {intent.safety_verdict} не допущен к входу"))

    # Размер одной позиции (AC-07).
    max_position_usd = policy.max_position_pct * equity
    if intent.notional_usd > max_position_usd:
        reasons.append(RiskReason(
            "position_size_exceeded",
            f"Размер ${intent.notional_usd:.0f} > лимита позиции ${max_position_usd:.0f} "
            f"({policy.max_position_pct*100:.1f}% equity)"))

    # Совокупная экспозиция.
    max_exposure_usd = policy.max_exposure_pct * equity
    if portfolio.gross_exposure_usd + intent.notional_usd > max_exposure_usd:
        reasons.append(RiskReason(
            "exposure_exceeded",
            f"Экспозиция ${portfolio.gross_exposure_usd + intent.notional_usd:.0f} "
            f"> лимита ${max_exposure_usd:.0f} ({policy.max_exposure_pct*100:.0f}% equity)"))

    # Максимум открытых позиций.
    if portfolio.open_count >= policy.max_open_positions:
        reasons.append(RiskReason(
            "max_open_positions",
            f"Открыто {portfolio.open_count} позиций ≥ лимита {policy.max_open_positions}"))

    # Гейты рыночных данных (проскальзывание/ликвидность/TTL). None = нет данных → fail-closed.
    if policy.enforce_market_data:
        if intent.expected_slippage_pct is None:
            reasons.append(RiskReason("slippage_unknown", "Нет оценки проскальзывания"))
        elif intent.expected_slippage_pct > policy.max_slippage_pct:
            reasons.append(RiskReason(
                "slippage_exceeded",
                f"Проскальзывание {intent.expected_slippage_pct*100:.2f}% "
                f"> лимита {policy.max_slippage_pct*100:.2f}%"))

        if intent.liquidity_usd is None:
            reasons.append(RiskReason("liquidity_unknown", "Нет данных о ликвидности"))
        elif intent.liquidity_usd < policy.min_liquidity_usd:
            reasons.append(RiskReason(
                "liquidity_too_low",
                f"Ликвидность ${intent.liquidity_usd:.0f} < минимума "
                f"${policy.min_liquidity_usd:.0f}"))

        if intent.quote_age_seconds is None:
            reasons.append(RiskReason("quote_age_unknown", "Нет данных о возрасте котировки"))
        elif intent.quote_age_seconds > policy.max_quote_age_seconds:
            reasons.append(RiskReason(
                "quote_too_old",
                f"Котировка {intent.quote_age_seconds:.0f}с старше TTL "
                f"{policy.max_quote_age_seconds:.0f}с"))

    # Дневной лимит убытка: при превышении новые входы запрещены.
    daily_loss_limit_usd = policy.daily_loss_limit_pct * equity
    if portfolio.realized_pnl_today_usd <= -daily_loss_limit_usd:
        reasons.append(RiskReason(
            "daily_loss_limit",
            f"Дневной убыток ${-portfolio.realized_pnl_today_usd:.0f} ≥ лимита "
            f"${daily_loss_limit_usd:.0f} ({policy.daily_loss_limit_pct*100:.0f}% equity)"))

    return reasons
