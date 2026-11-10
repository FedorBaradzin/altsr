"""Аварийная остановка (kill switch) — ТЗ §6.

Состояние — неизменяемый снимок. Хранение/персистентность — ответственность вызывающего
слоя (Redis/БД); здесь только чистые переходы и реестр причин.

При активной остановке новые входы запрещены. Закрытие позиций допускается только по
безопасному пути и только при достоверных котировках (см. engine.evaluate).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

# Условия аварийной остановки (ТЗ §6). Код → человекочитаемое описание.
TRIP_REASONS: dict[str, str] = {
    "market_data_lost": "Потеря достоверных рыночных данных",
    "balance_mismatch": "Расхождение on-chain баланса и внутреннего учёта",
    "key_compromise": "Подозрение на компрометацию ключа или делегации",
    "limit_breach": "Нарушение лимитов",
    "ambiguous_tx": "Неоднозначный статус отправленной транзакции",
    "contract_change": "Критическое изменение контракта токена",
    "mass_execution_errors": "Массовые ошибки исполнения",
    "user_revoked": "Отзыв полномочий пользователем",
    "admin_manual": "Ручная остановка администратором",
}


@dataclass(frozen=True)
class KillSwitchState:
    active: bool
    reason: str | None = None
    tripped_at: datetime | None = None


def trip(reason_code: str, *, now: datetime | None = None) -> KillSwitchState:
    """Активировать остановку с указанной причиной."""
    if reason_code not in TRIP_REASONS:
        raise ValueError(f"Неизвестная причина остановки: {reason_code!r}")
    return KillSwitchState(
        active=True,
        reason=reason_code,
        tripped_at=now or datetime.now(timezone.utc),
    )


def clear() -> KillSwitchState:
    """Снять остановку (только после проверки — ответственность вызывающего слоя)."""
    return KillSwitchState(active=False, reason=None, tripped_at=None)
