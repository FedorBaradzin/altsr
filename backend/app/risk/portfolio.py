"""Portfolio-мультиплексор (T9, видео 71). Чистая логика, без сети/БД.

N параллельных paper-инстансов делят общий банк поровну (1/N на инстанс). Над всеми —
общий kill-switch: при превышении совокупной просадки входы гасятся во ВСЕХ инстансах.
Совокупный риск не превышает банк, агрегаты = сумма инстансов.

Honest: диверсификация по инстансам не отменяет убытков; общий kill-switch ограничивает
совокупную просадку, но не гарантирует её отсутствие.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Instance:
    """Снимок одного paper-инстанса."""

    key: str
    deployed_usd: float = 0.0
    realized_pnl_usd: float = 0.0


@dataclass(frozen=True)
class MultiplexerConfig:
    total_bank_usd: float
    n_instances: int
    # Совокупная просадка реализованного P&L, после которой — общий kill-switch.
    global_stop_pct: float = 0.20

    def __post_init__(self) -> None:
        if self.total_bank_usd < 0:
            raise ValueError("total_bank_usd ≥ 0")
        if self.n_instances < 1:
            raise ValueError("n_instances ≥ 1")


@dataclass(frozen=True)
class AggregateState:
    total_deployed_usd: float
    total_realized_pnl_usd: float
    drawdown_pct: float


def per_instance_bank(cfg: MultiplexerConfig) -> float:
    """Доля банка на инстанс = банк / N."""
    return cfg.total_bank_usd / cfg.n_instances


def aggregate(instances: list[Instance], cfg: MultiplexerConfig) -> AggregateState:
    """Агрегаты по всем инстансам. drawdown_pct считается от общего банка."""
    deployed = sum(i.deployed_usd for i in instances)
    pnl = sum(i.realized_pnl_usd for i in instances)
    dd = 0.0
    if cfg.total_bank_usd > 0:
        dd = max(0.0, -pnl / cfg.total_bank_usd)
    return AggregateState(deployed, pnl, dd)


def global_kill(instances: list[Instance], cfg: MultiplexerConfig) -> bool:
    """Взведён ли общий kill-switch (совокупная просадка ≥ порога)."""
    if cfg.global_stop_pct <= 0:
        return False
    return aggregate(instances, cfg).drawdown_pct >= cfg.global_stop_pct


def can_instance_enter(
    instance: Instance,
    cfg: MultiplexerConfig,
    *,
    new_notional_usd: float = 0.0,
    global_killed: bool | None = None,
) -> tuple[bool, str | None]:
    """Можно ли инстансу открыть вход. global_killed переопределяет при явной передаче."""
    if global_killed is None:
        global_killed = False
    if global_killed:
        return False, "общий kill-switch активен"
    cap = per_instance_bank(cfg)
    if instance.deployed_usd + new_notional_usd > cap:
        return False, (f"доля инстанса исчерпана: "
                       f"${instance.deployed_usd + new_notional_usd:,.0f} > ${cap:,.0f}")
    return True, None
