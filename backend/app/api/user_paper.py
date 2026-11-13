"""Персональный бумажный счёт пользователя (с нуля).

Детерминированная симуляция: стоимость позиции считается из bias+seed+времени,
поэтому backend и фронт дают одинаковую цифру без хранения «цены» на каждый тик.
Реальных денег нет — это тренажёр стратегии поверх радара.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.service import current_user
from ..db import get_session
from ..models import (
    AutotradeConfig,
    Token,
    User,
    UserPaperAccount,
    UserPaperPosition,
    UserPaperTrade,
)
from ..paper.pricing import get_live_price_map
from ..schemas import (
    BuyPaperIn,
    OpenPaperIn,
    UserPaperOut,
    UserPaperPositionOut,
    UserPaperTradeOut,
)

router = APIRouter(prefix="/api/paper", tags=["paper-user"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _factor(pos: UserPaperPosition) -> float:
    """Legacy-оценка: детерминированная формула (для позиций без реальной цены)."""
    opened = pos.opened_at
    if opened.tzinfo is None:
        opened = opened.replace(tzinfo=timezone.utc)
    mins = max(0.0, (_utcnow() - opened).total_seconds() / 60.0)
    trend = pos.bias * (1.0 - math.exp(-mins / 90.0))
    wobble = 0.05 * math.sin(mins / 11.0 + pos.seed)
    return max(0.02, 1.0 + trend + wobble)


def _pos_keys(positions: list[UserPaperPosition]) -> set[tuple[str, str]]:
    """(chain, address) для позиций, которые можно оценить по реальной цене."""
    return {
        (p.chain.lower(), p.address.lower())
        for p in positions
        if p.address and p.entry_price and p.entry_price > 0
    }


def _ratio(pos: UserPaperPosition, price_map: dict[tuple[str, str], float]) -> float:
    """Множитель текущая/входная. Реальная цена с DEX, иначе — формула (legacy)."""
    if pos.address and pos.entry_price and pos.entry_price > 0:
        cur = price_map.get((pos.chain.lower(), pos.address.lower()))
        if cur and cur > 0:
            return cur / pos.entry_price
    return _factor(pos)


async def _resolve_token(
    session: AsyncSession, chain: str | None, symbol: str | None
) -> Token | None:
    """Самый свежий токен по символу (и сети, если задана) — для ручной покупки."""
    if not symbol:
        return None
    q = select(Token).where(Token.symbol == symbol)
    if chain and chain != "—":
        q = q.where(Token.chain == chain)
    q = q.order_by(Token.discovered_at.desc()).limit(1)
    return (await session.execute(q)).scalar_one_or_none()


async def _get_account(session: AsyncSession, user: User) -> UserPaperAccount | None:
    return (
        await session.execute(
            select(UserPaperAccount).where(UserPaperAccount.user_id == user.id)
        )
    ).scalar_one_or_none()


async def _assemble(session: AsyncSession, acc: UserPaperAccount | None) -> UserPaperOut:
    if acc is None:
        return UserPaperOut(opened=False)
    positions = (
        await session.execute(
            select(UserPaperPosition).where(UserPaperPosition.account_id == acc.id)
        )
    ).scalars().all()
    trades = (
        await session.execute(
            select(UserPaperTrade)
            .where(UserPaperTrade.account_id == acc.id)
            .order_by(UserPaperTrade.closed_at.desc())
        )
    ).scalars().all()

    price_map = await get_live_price_map(_pos_keys(list(positions)))
    pos_out: list[UserPaperPositionOut] = []
    equity = acc.cash
    for p in positions:
        f = _ratio(p, price_map)
        val = p.amount_usd * f
        equity += val
        pos_out.append(
            UserPaperPositionOut(
                id=p.id, symbol=p.symbol, chain=p.chain, amount_usd=p.amount_usd,
                value=round(val, 2), pnl_pct=round((f - 1.0) * 100.0, 2),
                opened_at=p.opened_at,
            )
        )

    pnl_pct = (
        ((equity - acc.start_balance) / acc.start_balance * 100.0)
        if acc.start_balance else None
    )
    win_rate = None
    if trades:
        wins = sum(1 for t in trades if t.pnl_usd >= 0)
        win_rate = round(wins / len(trades) * 100)

    return UserPaperOut(
        opened=True,
        start_balance=acc.start_balance,
        cash=round(acc.cash, 2),
        equity=round(equity, 2),
        pnl_pct=round(pnl_pct, 2) if pnl_pct is not None else None,
        win_rate=win_rate,
        positions=pos_out,
        trades=[
            UserPaperTradeOut(
                symbol=t.symbol, chain=t.chain, amount_usd=t.amount_usd,
                exit_value=round(t.exit_value, 2), pnl_usd=round(t.pnl_usd, 2),
                pnl_pct=round(t.pnl_pct, 2), closed_at=t.closed_at,
            )
            for t in trades
        ],
    )


@router.get("/me", response_model=UserPaperOut)
async def get_my_paper(
    user: User = Depends(current_user), session: AsyncSession = Depends(get_session),
) -> UserPaperOut:
    return await _assemble(session, await _get_account(session, user))


@router.post("/me/open", response_model=UserPaperOut)
async def open_my_paper(
    body: OpenPaperIn,
    user: User = Depends(current_user), session: AsyncSession = Depends(get_session),
) -> UserPaperOut:
    acc = await _get_account(session, user)
    if acc is None:
        bal = max(0.0, round(body.start_balance))
        acc = UserPaperAccount(user_id=user.id, start_balance=bal, cash=bal)
        session.add(acc)
        await session.commit()
        await session.refresh(acc)
    return await _assemble(session, acc)


@router.post("/me/buy", response_model=UserPaperOut)
async def buy_my_paper(
    body: BuyPaperIn,
    user: User = Depends(current_user), session: AsyncSession = Depends(get_session),
) -> UserPaperOut:
    acc = await _get_account(session, user)
    if acc is None:
        raise HTTPException(status_code=400, detail="Счёт не открыт")
    amount = round(body.amount_usd)
    if amount < 1 or amount > acc.cash:
        raise HTTPException(status_code=400, detail="Недостаточно средств или неверная сумма")
    bias = 0.2 + random.uniform(-0.3, 0.4)
    # Пытаемся привязать реальную цену: ищем токен по (chain, symbol) и берём цену с DEX.
    chain = (body.chain or "—")[:32]
    entry_price: float | None = None
    address: str | None = None
    pair_address: str | None = None
    tok = await _resolve_token(session, body.chain, body.symbol)
    if tok and tok.address:
        pm = await get_live_price_map({(tok.chain.lower(), tok.address.lower())})
        px = pm.get((tok.chain.lower(), tok.address.lower()))
        if px and px > 0:
            entry_price, address, pair_address, chain = px, tok.address, tok.pair_address, tok.chain
    acc.cash -= amount
    session.add(
        UserPaperPosition(
            account_id=acc.id, symbol=body.symbol[:64], chain=chain,
            amount_usd=amount, bias=bias, seed=random.uniform(0, 6.28),
            entry_price=entry_price, address=address, pair_address=pair_address,
        )
    )
    await session.commit()
    await session.refresh(acc)
    return await _assemble(session, acc)


@router.post("/me/close/{position_id}", response_model=UserPaperOut)
async def close_my_paper(
    position_id: int,
    user: User = Depends(current_user), session: AsyncSession = Depends(get_session),
) -> UserPaperOut:
    acc = await _get_account(session, user)
    if acc is None:
        raise HTTPException(status_code=400, detail="Счёт не открыт")
    pos = (
        await session.execute(
            select(UserPaperPosition).where(
                UserPaperPosition.id == position_id,
                UserPaperPosition.account_id == acc.id,
            )
        )
    ).scalar_one_or_none()
    if pos is None:
        raise HTTPException(status_code=404, detail="Позиция не найдена")
    price_map = await get_live_price_map(_pos_keys([pos]))
    f = _ratio(pos, price_map)
    val = pos.amount_usd * f
    acc.cash += val
    session.add(
        UserPaperTrade(
            account_id=acc.id, symbol=pos.symbol, chain=pos.chain,
            amount_usd=pos.amount_usd, exit_value=val,
            pnl_usd=val - pos.amount_usd, pnl_pct=(f - 1.0) * 100.0,
        )
    )
    await session.delete(pos)
    await session.commit()
    await session.refresh(acc)
    return await _assemble(session, acc)


@router.post("/me/reset", response_model=UserPaperOut)
async def reset_my_paper(
    user: User = Depends(current_user), session: AsyncSession = Depends(get_session),
) -> UserPaperOut:
    acc = await _get_account(session, user)
    if acc is not None:
        await session.execute(
            delete(UserPaperAccount).where(UserPaperAccount.id == acc.id)
        )
    # Сброс счёта обнуляет и дневной счётчик автотрейда — иначе бот думает, что
    # дневной кап уже выбран (day_spent висит с прошлой сессии) и не открывает позиций.
    cfg = (
        await session.execute(
            select(AutotradeConfig).where(AutotradeConfig.user_id == user.id)
        )
    ).scalar_one_or_none()
    if cfg is not None:
        cfg.day_spent_usd = 0.0
        cfg.last_run_at = None
    await session.commit()
    return UserPaperOut(opened=False)
