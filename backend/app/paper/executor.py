"""Бумажный исполнитель: открытие по сигналу, ведение позиций, дневные лимиты.

Леджер: cash уменьшается на размер ставки при открытии, растёт на выручку при выходе.
equity = cash + текущая стоимость открытых позиций. Издержки круга (cost_pct)
вычитаются из выручки при продаже — поэтому «вход-выход во флэте» уже в минусе.

ВСЁ БУМАЖНОЕ. Реальные ключи/кошельки не задействованы.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..models import PaperAccount, PaperPosition, Signal, Token
from ..risk.engine import evaluate as risk_evaluate
from ..risk.policy import RiskPolicy
from ..risk.types import PortfolioState, TradeIntent
from ..risk.types import Position as RiskPosition
from .exits import ExitConfig, PositionState, evaluate_exit

logger = logging.getLogger("altsr.paper.executor")

PriceFn = Callable[[str, str], Awaitable[float | None]]


def paper_risk_policy(s: Settings) -> RiskPolicy:
    """Risk-policy для paper: лимиты портфеля из настроек бумажной торговли.

    Safety и рыночные гейты (проскальзывание/ликвидность/TTL) в paper выключены —
    эти проверки уже выполнены выше по конвейеру (safety + signal), а на шаге бумажного
    исполнения достоверных котировок DEX нет. Для live оба гейта будут включены.
    """
    start = max(float(s.paper_start_balance), 1.0)
    exposure_frac = (s.paper_max_positions * s.paper_position_size_usd / start) * 1.2
    return RiskPolicy(
        version="paper-v1",
        max_position_pct=max(0.02, (s.paper_position_size_usd / start) * 3.0),
        max_exposure_pct=max(0.25, exposure_frac),
        daily_loss_limit_pct=max(s.paper_daily_loss_limit_usd / start, 1e-6),
        max_open_positions=s.paper_max_positions,
        max_slippage_pct=1.0,
        min_liquidity_usd=0.0,
        max_quote_age_seconds=1e9,
        enforce_safety=False,
        enforce_market_data=False,
    )


async def _portfolio_state(
    session: AsyncSession, acc: PaperAccount, now: datetime
) -> PortfolioState:
    """Снимок бумажного портфеля для Risk Engine: equity, открытые позиции, дневной P&L."""
    open_positions = (
        await session.execute(select(PaperPosition).where(PaperPosition.status == "open"))
    ).scalars().all()
    risk_positions: list[RiskPosition] = []
    gross = 0.0
    for p in open_positions:
        ratio = (p.last_price / p.entry_price) if p.entry_price else 1.0
        value = p.size_usd * p.remaining_fraction * ratio
        gross += value
        risk_positions.append(RiskPosition(f"{p.chain}:{p.address}", value))
    equity = acc.cash + gross
    realized_today = await _today_realized(session, now)
    return PortfolioState(
        equity_usd=equity,
        open_positions=tuple(risk_positions),
        realized_pnl_today_usd=realized_today,
        data_fresh=True,
    )


def config_from_settings(s: Settings) -> ExitConfig:
    return ExitConfig(
        hard_stop_pct=s.paper_hard_stop_pct,
        arm_after_profit_pct=s.paper_arm_after_profit_pct,
        trailing_stop_pct=s.paper_trailing_stop_pct,
        tp_x=s.paper_take_profit_x,
        tp_fraction=s.paper_take_profit_fraction,
        stall_minutes=s.paper_stall_minutes,
        max_hold_minutes=s.paper_max_hold_minutes,
    )


async def get_or_create_account(session: AsyncSession, s: Settings) -> PaperAccount:
    acc = (
        await session.execute(select(PaperAccount).where(PaperAccount.id == 1))
    ).scalar_one_or_none()
    if acc is None:
        acc = PaperAccount(
            id=1, start_balance=s.paper_start_balance, cash=s.paper_start_balance,
            realized_pnl=0.0, updated_at=datetime.now(timezone.utc),
        )
        session.add(acc)
        await session.flush()
    return acc


async def _count_open(session: AsyncSession) -> int:
    return (
        await session.execute(
            select(func.count()).select_from(PaperPosition).where(PaperPosition.status == "open")
        )
    ).scalar_one()


async def _today_realized(session: AsyncSession, now: datetime) -> float:
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    val = (
        await session.execute(
            select(func.coalesce(func.sum(PaperPosition.realized_pnl_usd), 0.0))
            .where(PaperPosition.closed_at.is_not(None), PaperPosition.closed_at >= start)
        )
    ).scalar_one()
    return float(val)


def _minutes(a: datetime, b: datetime) -> float:
    if a.tzinfo is None:
        a = a.replace(tzinfo=timezone.utc)
    if b.tzinfo is None:
        b = b.replace(tzinfo=timezone.utc)
    return max(0.0, (a - b).total_seconds() / 60.0)


async def open_from_signals(
    session: AsyncSession, s: Settings, get_price: PriceFn, now: datetime
) -> int:
    acc = await get_or_create_account(session, s)

    # Дневной лимит убытка → стоп новых покупок.
    if await _today_realized(session, now) <= -abs(s.paper_daily_loss_limit_usd):
        logger.info("Дневной лимит убытка достигнут — новые покупки остановлены")
        return 0

    policy = paper_risk_policy(s)
    opened = 0
    # Сигналы без бумажной позиции.
    stmt = (
        select(Signal, Token.symbol)
        .join(Token, Token.id == Signal.token_id)
        .outerjoin(PaperPosition, PaperPosition.token_id == Signal.token_id)
        .where(PaperPosition.id.is_(None))
        .order_by(Signal.created_at.desc())
    )
    rows = (await session.execute(stmt)).all()
    for sig, symbol in rows:
        if await _count_open(session) >= s.paper_max_positions:
            break
        if acc.cash < s.paper_position_size_usd:
            logger.info("Недостаточно бумажного кэша для новой позиции")
            break
        # Входим только в сигналы с достаточной уверенностью — меньше, но
        # качественнее сделок (снижает просадку и повышает win-rate).
        if (sig.confidence or 0.0) < s.signal_min_confidence:
            continue

        # Единый гейт: Risk Engine проверяет лимиты портфеля перед КАЖДЫМ входом.
        intent = TradeIntent(
            side="BUY",
            token_key=f"{sig.chain}:{sig.address}",
            chain=sig.chain,
            token_address=sig.address,
            notional_usd=s.paper_position_size_usd,
            recipient="paper",
            safety_verdict="PASS",
            strategy="paper",
            is_exit=False,
        )
        state = await _portfolio_state(session, acc, now)
        decision = risk_evaluate(intent, policy, state, now=now)
        if decision.blocked:
            logger.info(
                "Risk Engine заблокировал вход %s:%s — %s",
                sig.chain, sig.address, ", ".join(r.code for r in decision.reasons),
            )
            continue

        price = await get_price(sig.chain, sig.address)
        if price is None or price <= 0:
            continue
        acc.cash -= s.paper_position_size_usd
        pos = PaperPosition(
            token_id=sig.token_id, chain=sig.chain, address=sig.address, symbol=symbol,
            status="open", size_usd=s.paper_position_size_usd, entry_price=price,
            peak_price=price, last_price=price, remaining_fraction=1.0, tp_taken=False,
            realized_pnl_usd=0.0, opened_at=now, last_high_at=now,
        )
        session.add(pos)
        await session.flush()
        opened += 1
        logger.info("Открыта paper-позиция %s:%s @ %.8f", sig.chain, sig.address, price)

    acc.updated_at = now
    await session.flush()
    return opened


def _sell(pos: PaperPosition, fraction: float, price: float, cost_pct: float) -> float:
    """Продать долю fraction (от первоначальной) по цене price. Возвращает выручку."""
    gross = pos.size_usd * fraction * (price / pos.entry_price)
    proceeds = gross * (1 - cost_pct)
    cost_basis = pos.size_usd * fraction
    pos.realized_pnl_usd += proceeds - cost_basis
    pos.remaining_fraction = max(0.0, pos.remaining_fraction - fraction)
    return proceeds


async def process_positions(
    session: AsyncSession, s: Settings, get_price: PriceFn, now: datetime
) -> int:
    cfg = config_from_settings(s)
    acc = await get_or_create_account(session, s)
    closed = 0

    positions = (
        await session.execute(select(PaperPosition).where(PaperPosition.status == "open"))
    ).scalars().all()

    for pos in positions:
        price = await get_price(pos.chain, pos.address)
        if price is None or price <= 0:
            continue
        pos.last_price = price
        if price > pos.peak_price:
            pos.peak_price = price
            pos.last_high_at = now

        st = PositionState(
            entry_price=pos.entry_price, peak_price=pos.peak_price, price=price,
            minutes_since_open=_minutes(now, pos.opened_at),
            minutes_since_high=_minutes(now, pos.last_high_at),
            tp_taken=pos.tp_taken,
        )
        action = evaluate_exit(st, cfg)

        if action.kind == "hold":
            continue

        if action.kind == "partial":
            acc.cash += _sell(pos, action.fraction, price, s.paper_cost_pct)
            pos.tp_taken = True
            logger.info("Частичный выход %s: %s", pos.address, action.reason)
            continue

        # close — продаём остаток
        acc.cash += _sell(pos, pos.remaining_fraction, price, s.paper_cost_pct)
        pos.status = "closed"
        pos.closed_at = now
        pos.exit_reason = action.reason
        pos.pnl_pct = round(pos.realized_pnl_usd / pos.size_usd * 100, 2)
        acc.realized_pnl += pos.realized_pnl_usd
        closed += 1
        logger.info("Закрыта позиция %s: %s pnl=%.2f", pos.address, action.reason,
                    pos.realized_pnl_usd)

    acc.updated_at = now
    await session.flush()
    return closed
