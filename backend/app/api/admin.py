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
    ReferralPayout,
    Signal,
    Token,
    User,
)
from ..referral import service as referral_service
from ..referral.rate import OVERRIDE_MAX_RATE, OVERRIDE_MIN_RATE

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


@router.get("/referrals")
async def list_referrals(
    session: AsyncSession = Depends(get_session), limit: int = Query(200, ge=1, le=1000),
) -> list[dict]:
    """Рефереры (пользователи с ≥1 приглашённым) + активные, заработок, баланс."""
    referrer_ids = (
        await session.execute(
            select(User.referred_by_id)
            .where(User.referred_by_id.is_not(None))
            .distinct()
        )
    ).scalars().all()
    if not referrer_ids:
        return []
    rows = (
        await session.execute(
            select(User).where(User.id.in_(referrer_ids)).limit(limit)
        )
    ).scalars().all()
    out: list[dict] = []
    for u in rows:
        active = await referral_service.active_referrals(session, u.id)
        out.append({
            "user_id": u.id,
            "display_name": u.display_name,
            "email": u.email,
            "referral_code": u.referral_code,
            "active_referrals": active,
            "earned_total": round(await referral_service.earned_total(session, u.id), 2),
            "balance": await referral_service.balance(session, u.id),
            "rate_override": u.referral_rate_override,
        })
    out.sort(key=lambda r: r["earned_total"], reverse=True)
    return out


@router.post("/referrals/{user_id}/rate")
async def set_referral_rate(
    user_id: int, rate: float | None = Body(default=None, embed=True),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Задать индивидуальную ставку (0.30–0.50) или null, чтобы сбросить к авто-ставке."""
    if rate is not None and not (OVERRIDE_MIN_RATE <= rate <= OVERRIDE_MAX_RATE):
        raise HTTPException(
            status_code=400,
            detail=f"Ставка должна быть в диапазоне {OVERRIDE_MIN_RATE}–{OVERRIDE_MAX_RATE} или null",
        )
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    user.referral_rate_override = rate
    await session.commit()
    return {"ok": True, "user_id": user_id, "rate_override": rate}


@router.get("/referral-payouts")
async def list_referral_payouts(
    session: AsyncSession = Depends(get_session),
    status: str | None = Query(default=None),
    limit: int = Query(200, ge=1, le=1000),
) -> list[dict]:
    stmt = select(ReferralPayout).order_by(ReferralPayout.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(ReferralPayout.status == status)
    rows = (await session.execute(stmt)).scalars().all()
    return [{
        "id": p.id, "referrer_id": p.referrer_id, "amount_usd": p.amount_usd,
        "status": p.status, "address": p.address, "note": p.note,
        "created_at": p.created_at.isoformat(),
        "paid_at": p.paid_at.isoformat() if p.paid_at else None,
    } for p in rows]


@router.post("/referral-payouts/{payout_id}/status")
async def set_referral_payout_status(
    payout_id: int, status: str = Body(...), note: str | None = Body(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Отметить выплату как paid или rejected (при paid проставляется paid_at)."""
    if status not in ("pending", "paid", "rejected"):
        raise HTTPException(status_code=400, detail="Статус: pending|paid|rejected")
    payout = (
        await session.execute(select(ReferralPayout).where(ReferralPayout.id == payout_id))
    ).scalar_one_or_none()
    if payout is None:
        raise HTTPException(status_code=404, detail="Выплата не найдена")
    payout.status = status
    if note is not None:
        payout.note = note
    payout.paid_at = datetime.now(timezone.utc) if status == "paid" else None
    await session.commit()
    return {"ok": True, "id": payout_id, "status": status}


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
