"""Админ-панель: обзор, пользователи, тарифы вручную, платежи, флаги. Только для админа."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.service import TIER_RANK, effective_tier, require_admin
from ..config import Settings, get_settings
from ..db import get_session
from ..models import (
    Article,
    NewsItem,
    PaperAccount,
    PaperPosition,
    Payment,
    Signal,
    Token,
    User,
)

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


async def _count(session: AsyncSession, model, *where) -> int:
    stmt = select(func.count()).select_from(model).where(*where)
    return (await session.execute(stmt)).scalar_one()


@router.get("/overview")
async def overview(session: AsyncSession = Depends(get_session)) -> dict:
    acc = (
        await session.execute(select(PaperAccount).where(PaperAccount.id == 1))
    ).scalar_one_or_none()
    return {
        "tokens": await _count(session, Token),
        "signals": await _count(session, Signal),
        "positions_open": await _count(session, PaperPosition, PaperPosition.status == "open"),
        "positions_closed": await _count(session, PaperPosition, PaperPosition.status == "closed"),
        "users": await _count(session, User),
        "payments_paid": await _count(session, Payment, Payment.status.in_(
            ("finished", "confirmed", "sending"))),
        "articles": await _count(session, Article),
        "news": await _count(session, NewsItem),
        "paper_equity": round(acc.cash, 2) if acc else None,
        "paper_realized": round(acc.realized_pnl, 2) if acc else None,
    }


@router.get("/users")
async def list_users(
    session: AsyncSession = Depends(get_session), limit: int = Query(100, ge=1, le=500),
) -> list[dict]:
    rows = (
        await session.execute(select(User).order_by(User.created_at.desc()).limit(limit))
    ).scalars().all()
    return [{
        "id": u.id, "auth_method": u.auth_method, "subject": u.subject, "email": u.email,
        "display_name": u.display_name, "tier": effective_tier(u),
        "tier_expires_at": u.tier_expires_at.isoformat() if u.tier_expires_at else None,
        "created_at": u.created_at.isoformat(),
    } for u in rows]


@router.post("/users/{user_id}/tier")
async def set_tier(
    user_id: int, tier: str = Body(...), days: int = Body(default=30),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if tier not in TIER_RANK:
        raise HTTPException(status_code=400, detail="Неизвестный тариф")
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    user.tier = tier
    user.tier_expires_at = (
        None if tier == "free" else datetime.now(timezone.utc) + timedelta(days=days)
    )
    await session.commit()
    return {"ok": True, "user_id": user_id, "tier": tier}


@router.get("/payments")
async def list_payments(
    session: AsyncSession = Depends(get_session), limit: int = Query(100, ge=1, le=500),
) -> list[dict]:
    rows = (
        await session.execute(select(Payment).order_by(Payment.created_at.desc()).limit(limit))
    ).scalars().all()
    return [{
        "id": p.id, "user_id": p.user_id, "tier": p.tier, "status": p.status,
        "amount_usd": p.amount_usd, "invoice_id": p.invoice_id,
        "created_at": p.created_at.isoformat(),
    } for p in rows]


@router.get("/flags")
async def flags(settings: Settings = Depends(get_settings)) -> dict:
    """Текущие фиче-флаги (read-only; меняются через .env + рестарт)."""
    return {
        "live_trading_enabled": settings.live_trading_enabled,
        "content_enabled": settings.content_enabled,
        "articles_per_day": settings.articles_per_day,
        "ai_enabled": settings.ai_enabled and bool(settings.ai_api_key),
        "metricool_enabled": settings.metricool_enabled,
        "telegram_configured": bool(settings.telegram_bot_token),
        "nowpayments_configured": bool(settings.nowpayments_api_key),
        "google_configured": bool(settings.google_client_id),
    }
