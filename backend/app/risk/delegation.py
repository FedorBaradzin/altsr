"""Проверка ограниченных полномочий делегации (ТЗ §2.1).

Чистые функции. Делегация задаёт строгие границы того, что исполнитель вправе делать
от имени пользователя: сети, токены, получатели, стратегии, лимиты расходов и срок.

Философия fail-closed:
- пустой список сетей → ни одна сеть не разрешена;
- пустой список стратегий → ни одна стратегия не разрешена;
- пустой список получателей → разрешён только владелец;
- пустой список токенов → любой токен (отбор делает Safety Engine, не делегация);
- неустановленные лимиты (на сделку / дневной ≤ 0) → отказ.
Недельный лимит ≤ 0 трактуется как «не задан» (не применяется).

Сравнение адресов — регистронезависимое (checksum EVM / case Solana не должны ломать проверку).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .types import RiskReason, TradeIntent


@dataclass(frozen=True)
class DelegationPolicy:
    delegation_id: str
    owner: str
    revoked: bool = False
    expires_at: datetime | None = None
    allowed_chains: tuple[str, ...] = field(default=())
    allowed_tokens: tuple[str, ...] = field(default=())
    allowed_recipients: tuple[str, ...] = field(default=())
    allowed_strategies: tuple[str, ...] = field(default=())
    max_trade_usd: float = 0.0
    daily_cap_usd: float = 0.0
    weekly_cap_usd: float = 0.0


@dataclass(frozen=True)
class SpendState:
    """Уже израсходованный торговый бюджет (считается вызывающим слоем из ledger)."""

    spent_today_usd: float = 0.0
    spent_week_usd: float = 0.0


def _norm(addr: str) -> str:
    return addr.strip().lower()


def _allowed_recipient(intent: TradeIntent, d: DelegationPolicy) -> bool:
    allowed = {_norm(d.owner), *(_norm(r) for r in d.allowed_recipients)}
    return _norm(intent.recipient) in allowed


def check(
    intent: TradeIntent,
    delegation: DelegationPolicy,
    spent: SpendState,
    *,
    now: datetime,
) -> list[RiskReason]:
    """Вернуть список блокирующих причин (пустой = делегация не возражает)."""
    reasons: list[RiskReason] = []

    # --- Действуют всегда (вход и выход) ---
    if delegation.revoked:
        reasons.append(RiskReason("delegation_revoked", "Делегация отозвана"))
    if delegation.expires_at is not None and now >= delegation.expires_at:
        reasons.append(RiskReason("delegation_expired", "Срок делегации истёк"))
    if not _allowed_recipient(intent, delegation):
        reasons.append(RiskReason(
            "recipient_not_allowed",
            f"Получатель {intent.recipient} не разрешён (только владелец/allowlist)",
        ))

    # --- Расход бюджета и allowlists проверяем только для нового входа (трата средств) ---
    if intent.is_entry:
        if intent.chain not in delegation.allowed_chains:
            reasons.append(RiskReason(
                "chain_not_allowed", f"Сеть {intent.chain} не в allowlist делегации"))
        if delegation.allowed_tokens and intent.token_key not in delegation.allowed_tokens:
            reasons.append(RiskReason(
                "token_not_allowed", f"Токен {intent.token_key} не в allowlist делегации"))
        if (intent.strategy or "") not in delegation.allowed_strategies:
            reasons.append(RiskReason(
                "strategy_not_allowed",
                f"Стратегия {intent.strategy!r} не разрешена этой делегацией"))

        # Лимиты расходов (AC-07).
        if delegation.max_trade_usd <= 0 or intent.notional_usd > delegation.max_trade_usd:
            reasons.append(RiskReason(
                "trade_cap_exceeded",
                f"Сделка ${intent.notional_usd:.0f} > лимита на сделку "
                f"${delegation.max_trade_usd:.0f}"))
        if (delegation.daily_cap_usd <= 0
                or spent.spent_today_usd + intent.notional_usd > delegation.daily_cap_usd):
            reasons.append(RiskReason(
                "daily_cap_exceeded",
                f"Дневной расход ${spent.spent_today_usd + intent.notional_usd:.0f} "
                f"> лимита ${delegation.daily_cap_usd:.0f}"))
        if (delegation.weekly_cap_usd > 0
                and spent.spent_week_usd + intent.notional_usd > delegation.weekly_cap_usd):
            reasons.append(RiskReason(
                "weekly_cap_exceeded",
                f"Недельный расход ${spent.spent_week_usd + intent.notional_usd:.0f} "
                f"> лимита ${delegation.weekly_cap_usd:.0f}"))

    return reasons
