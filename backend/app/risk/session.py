"""Session controller «ночная смена» (T5, видео 70). Чистая логика, без сети/БД.

Управляет торговой сессией инстанса: жёсткий потолок развёрнутого капитала
(budget_cap) и session-stop по просадке реализованного P&L, который взводит
kill-switch (ТЗ §6). Детерминированно; параметры — из конфига/YAML на инстанс.

Honest: session-stop ограничивает убыток сессии, но не гарантирует его отсутствие.
«Нет данных ≠ ноль»: при неизвестном equity вход запрещён (fail-closed).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import Settings


@dataclass(frozen=True)
class SessionConfig:
    """Параметры сессии инстанса.

    budget_cap_usd — максимум одновременно развёрнутого капитала (0 = без лимита);
    session_stop_pct — просадка реализованного P&L от стартового equity, после которой
    сессия останавливается и взводится kill-switch (напр. 0.20 = −20%).
    """

    budget_cap_usd: float = 0.0
    session_stop_pct: float = 0.20


@dataclass(frozen=True)
class SessionSnapshot:
    """Состояние сессии на момент решения."""

    start_equity_usd: float
    deployed_usd: float = 0.0          # сумма открытых позиций (оценка)
    realized_pnl_usd: float = 0.0      # реализованный P&L за сессию (отрицателен при убытке)

    @property
    def drawdown_pct(self) -> float:
        """Просадка реализованного P&L (>0 при убытке). 0, если equity неизвестен."""
        if self.start_equity_usd <= 0:
            return 0.0
        return max(0.0, -self.realized_pnl_usd / self.start_equity_usd)


@dataclass(frozen=True)
class SessionDecision:
    can_enter: bool
    trip_kill_switch: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def stopped(self) -> bool:
        return self.trip_kill_switch


def evaluate_session(
    snap: SessionSnapshot, cfg: SessionConfig, *, new_notional_usd: float = 0.0
) -> SessionDecision:
    """Можно ли открывать вход и не пора ли взводить kill-switch.

    new_notional_usd — размер планируемого входа (для проверки budget_cap).
    """
    reasons: list[str] = []
    trip = False
    can_enter = True

    # Нет достоверного equity → fail-closed (не входим).
    if snap.start_equity_usd <= 0:
        return SessionDecision(False, False, ("нет достоверного equity",))

    # Session-stop по просадке реализованного P&L → kill-switch, входы запрещены.
    if cfg.session_stop_pct > 0 and snap.drawdown_pct >= cfg.session_stop_pct:
        trip = True
        can_enter = False
        reasons.append(
            f"session-stop: просадка {snap.drawdown_pct*100:.1f}% ≥ "
            f"{cfg.session_stop_pct*100:.0f}%")

    # Budget cap: развёрнутый + новый вход не должны превышать потолок.
    if cfg.budget_cap_usd > 0:
        if snap.deployed_usd + new_notional_usd > cfg.budget_cap_usd:
            can_enter = False
            reasons.append(
                f"budget cap: ${snap.deployed_usd + new_notional_usd:,.0f} > "
                f"${cfg.budget_cap_usd:,.0f}")

    return SessionDecision(can_enter, trip, tuple(reasons))


def session_config_from_settings(s: Settings) -> SessionConfig:
    """Собрать SessionConfig из настроек инстанса (env/YAML)."""
    return SessionConfig(
        budget_cap_usd=s.session_budget_cap_usd,
        session_stop_pct=s.session_stop_pct,
    )
