"""Публичная read-only статистика бумажного счёта владельца — для лендинга.

Без авторизации. Отдаёт только агрегаты (equity / доходность / win-rate /
число позиций / реализованный P&L) по счёту первого ADMIN_IDENTIFIERS —
никаких адресов, символов или чужих данных. Нужно, чтобы на главной
показывать РЕАЛЬНЫЙ бумажный счёт автоторговли, а не демо-формулу.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_session
from ..models import User, UserPaperAccount
from .user_paper import _assemble

router = APIRouter(prefix="/api/public", tags=["public"])


async def _owner_account(session: AsyncSession) -> UserPaperAccount | None:
    """Счёт владельца: первый из ADMIN_IDENTIFIERS (email или subject), у кого
    реально открыт бумажный счёт. Идентификаторов может быть несколько, а счёт —
    только у одного из них, поэтому перебираем всех админов."""
    ids = get_settings().admin_identifier_list
    if not ids:
        return None
    users = (
        await session.execute(
            select(User).where(
                or_(
                    func.lower(User.email).in_(ids),
                    func.lower(User.subject).in_(ids),
                )
            )
        )
    ).scalars().all()
    for u in users:
        acc = (
            await session.execute(
                select(UserPaperAccount).where(UserPaperAccount.user_id == u.id)
            )
        ).scalar_one_or_none()
        if acc is not None:
            return acc
    return None


@router.get("/paper")
async def public_paper(session: AsyncSession = Depends(get_session)) -> dict:
    acc = await _owner_account(session)
    if acc is None:
        return {"opened": False}
    out = await _assemble(session, acc)
    realized = round(sum(t.pnl_usd for t in out.trades), 2)
    wins = sum(1 for t in out.trades if t.pnl_usd >= 0)
    return {
        "opened": True,
        "start": round(out.start_balance),
        "equity": round(out.equity),
        "cash": round(out.cash),
        "return_pct": out.pnl_pct,
        "win_rate": out.win_rate,
        "open_positions": len(out.positions),
        "closed": len(out.trades),
        "wins": wins,
        "losses": len(out.trades) - wins,
        "realized_pnl": realized,
    }
