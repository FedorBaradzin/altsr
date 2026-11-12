"""Симуляционный автотрейд: бот торгует на БУМАЖНОМ счёте пользователя по правилам.

Реальных денег нет и live-исполнения нет — это тренажёр стратегии поверх сигналов радара.
Каждый «тик» (/run) закрывает позиции по TP/стопу и открывает новые по свежим сигналам,
в пределах лимита на позицию и дневного капа. Доступно на тарифе Autonomous.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.service import TIER_RANK, current_user, effective_tier, is_admin
from ..config import Settings, get_settings
from ..db import get_session
from ..models import (
    AutotradeConfig,
    Signal,
    Token,
    User,
    UserPaperAccount,
    UserPaperPosition,
    UserPaperTrade,
)
from ..schemas import AutotradeConfigIn, AutotradeConfigOut, AutotradeRunOut
from .user_paper import _factor, _utcnow

router = APIRouter(prefix="/api/autotrade", tags=["autotrade"])

# Как далеко назад бот ищет свежие сигналы на каждом тике. Фиксированное окно, а не
# «с прошлого тика» — иначе после первого же прогона last_run_at==now и окно пустое.
LOOKBACK_HOURS = 6


def _require_autonomous(user: User, settings: Settings) -> None:
    if not is_admin(user, settings) and TIER_RANK.get(effective_tier(user), 0) < 2:
        raise HTTPException(status_code=402, detail="Автоторговля доступна на тарифе Autonomous")


async def _get_or_create_cfg(session: AsyncSession, user: User) -> AutotradeConfig:
    cfg = (
        await session.execute(select(AutotradeConfig).where(AutotradeConfig.user_id == user.id))
    ).scalar_one_or_none()
    if cfg is None:
        cfg = AutotradeConfig(user_id=user.id)
        session.add(cfg)
        await session.commit()
        await session.refresh(cfg)
    return cfg


def _as_out(cfg: AutotradeConfig) -> AutotradeConfigOut:
    return AutotradeConfigOut(
        enabled=cfg.enabled, max_position_usd=cfg.max_position_usd,
        daily_cap_usd=cfg.daily_cap_usd, min_confidence=cfg.min_confidence,
        tp_pct=cfg.tp_pct, stop_pct=cfg.stop_pct, chains=cfg.chains,
        day_spent_usd=round(cfg.day_spent_usd, 2), last_run_at=cfg.last_run_at,
    )


@router.get("/config", response_model=AutotradeConfigOut)
async def get_config(
    user: User = Depends(current_user), session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AutotradeConfigOut:
    _require_autonomous(user, settings)
    return _as_out(await _get_or_create_cfg(session, user))


@router.put("/config", response_model=AutotradeConfigOut)
async def put_config(
    body: AutotradeConfigIn,
    user: User = Depends(current_user), session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AutotradeConfigOut:
    _require_autonomous(user, settings)
    cfg = await _get_or_create_cfg(session, user)
    if body.enabled is not None:
        cfg.enabled = bool(body.enabled)
    if body.max_position_usd is not None:
        cfg.max_position_usd = max(1.0, min(100000.0, body.max_position_usd))
    if body.daily_cap_usd is not None:
        cfg.daily_cap_usd = max(1.0, min(1000000.0, body.daily_cap_usd))
    if body.min_confidence is not None:
        cfg.min_confidence = max(0.0, min(1.0, body.min_confidence))
    if body.tp_pct is not None:
        cfg.tp_pct = max(1.0, min(1000.0, body.tp_pct))
    if body.stop_pct is not None:
        cfg.stop_pct = max(1.0, min(100.0, body.stop_pct))
    if body.chains is not None:
        cfg.chains = body.chains[:128]
    cfg.updated_at = _utcnow()
    await session.commit()
    await session.refresh(cfg)
    return _as_out(cfg)


async def _ensure_account(session: AsyncSession, user: User, cfg: AutotradeConfig) -> UserPaperAccount:
    acc = (
        await session.execute(select(UserPaperAccount).where(UserPaperAccount.user_id == user.id))
    ).scalar_one_or_none()
    if acc is None:
        start = max(1000.0, cfg.daily_cap_usd * 2)
        acc = UserPaperAccount(user_id=user.id, start_balance=start, cash=start)
        session.add(acc)
        await session.commit()
        await session.refresh(acc)
    return acc


async def _tick_user(session: AsyncSession, acc: UserPaperAccount, cfg: AutotradeConfig) -> dict:
    """Один тик для уже загруженных account+cfg (используется и эндпоинтом, и фоновым тикером)."""
    now = _utcnow()
    today = now.strftime("%Y-%m-%d")
    if cfg.day_key != today:
        cfg.day_key = today
        cfg.day_spent_usd = 0.0

    positions = (
        await session.execute(
            select(UserPaperPosition).where(UserPaperPosition.account_id == acc.id)
        )
    ).scalars().all()

    # --- закрытие по TP/стопу ---
    closed = 0
    held: set[str] = set()
    for p in positions:
        pnl = (_factor(p) - 1.0) * 100.0
        if pnl >= cfg.tp_pct or pnl <= -cfg.stop_pct:
            val = p.amount_usd * _factor(p)
            acc.cash += val
            session.add(UserPaperTrade(
                account_id=acc.id, symbol=p.symbol, chain=p.chain,
                amount_usd=p.amount_usd, exit_value=val,
                pnl_usd=val - p.amount_usd, pnl_pct=pnl,
            ))
            await session.delete(p)
            closed += 1
        else:
            held.add(p.symbol.upper())

    # --- открытие по свежим сигналам ---
    # Всегда смотрим фиксированное окно назад (а не «с last_run_at»), иначе каждый тик
    # после первого видит пустое окно. От повторной покупки защищает дедуп по символу:
    # пропускаем всё, что уже держим ИЛИ уже закрывали на этом счёте.
    since = now - timedelta(hours=LOOKBACK_HOURS)
    traded = (
        await session.execute(
            select(UserPaperTrade.symbol).where(UserPaperTrade.account_id == acc.id)
        )
    ).scalars().all()
    for s in traded:
        if s:
            held.add(s.upper())
    want_chains = [c.strip().lower() for c in cfg.chains.split(",") if c.strip()]
    rows = (
        await session.execute(
            select(Signal, Token.symbol)
            .join(Token, Token.id == Signal.token_id)
            .where(
                Signal.side == "BUY",
                Signal.confidence >= cfg.min_confidence,
                Signal.created_at > since,
            )
            .order_by(Signal.confidence.desc())
            .limit(50)
        )
    ).all()

    opened = 0
    for sig, symbol in rows:
        if not symbol:
            continue
        sym = symbol.upper()
        if sym in held:
            continue
        if want_chains and sig.chain.lower() not in want_chains:
            continue
        amt = min(cfg.max_position_usd, acc.cash)
        if amt < 1:
            break
        if cfg.day_spent_usd + amt > cfg.daily_cap_usd:
            continue
        bias = 0.2 + random.uniform(-0.3, 0.4)
        session.add(UserPaperPosition(
            account_id=acc.id, symbol=sym, chain=sig.chain[:32],
            amount_usd=round(amt), bias=bias, seed=random.uniform(0, 6.28),
        ))
        acc.cash -= round(amt)
        cfg.day_spent_usd += round(amt)
        held.add(sym)
        opened += 1

    cfg.last_run_at = now
    await session.commit()

    # пересчёт equity
    positions = (
        await session.execute(
            select(UserPaperPosition).where(UserPaperPosition.account_id == acc.id)
        )
    ).scalars().all()
    equity = acc.cash + sum(p.amount_usd * _factor(p) for p in positions)
    return {
        "opened": opened, "closed": closed, "open_positions": len(positions),
        "day_spent_usd": round(cfg.day_spent_usd, 2), "equity": round(equity, 2),
    }


@router.post("/run", response_model=AutotradeRunOut)
async def run_tick(
    user: User = Depends(current_user), session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AutotradeRunOut:
    _require_autonomous(user, settings)
    cfg = await _get_or_create_cfg(session, user)
    if not cfg.enabled:
        return AutotradeRunOut(enabled=False, note="Автотрейд выключен")
    acc = await _ensure_account(session, user, cfg)
    r = await _tick_user(session, acc, cfg)
    return AutotradeRunOut(enabled=True, note=f"Открыто {r['opened']}, закрыто {r['closed']}", **r)


async def tick_all_enabled() -> int:
    """Фоновый прогон: один тик для всех включённых автотрейд-конфигов. Возвращает число обработанных."""
    from ..db import get_sessionmaker

    processed = 0
    async with get_sessionmaker()() as session:
        cfgs = (
            await session.execute(
                select(AutotradeConfig).where(AutotradeConfig.enabled.is_(True))
            )
        ).scalars().all()
        for cfg in cfgs:
            user = await session.get(User, cfg.user_id)
            if user is None:
                continue
            try:
                acc = await _ensure_account(session, user, cfg)
                await _tick_user(session, acc, cfg)
                processed += 1
            except Exception:  # noqa: BLE001
                await session.rollback()
    return processed
