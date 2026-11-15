"""Публичная read-only статистика бумажного счёта владельца — для лендинга.

Без авторизации. Отдаёт только агрегаты (equity / доходность / win-rate /
число позиций / реализованный P&L) по счёту первого ADMIN_IDENTIFIERS —
никаких адресов, символов или чужих данных. Нужно, чтобы на главной
показывать РЕАЛЬНЫЙ бумажный счёт автоторговли, а не демо-формулу.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_session
from ..models import User, UserPaperAccount
from .user_paper import _assemble

router = APIRouter(prefix="/api/public", tags=["public"])


async def _owner_account(session: AsyncSession) -> UserPaperAccount | None:
    """Счёт владельца = первый идентификатор из ADMIN_IDENTIFIERS (обычно e-mail)."""
    ids = get_settings().admin_identifier_list
    if not ids:
        return None
    user = (
        await session.execute(
            select(User).where(func.lower(User.email) == ids[0])
        )
    ).scalar_one_or_none()
    if user is None:
        return None
    return (
        await session.execute(
            select(UserPaperAccount).where(UserPaperAccount.user_id == user.id)
        )
    ).scalar_one_or_none()


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
