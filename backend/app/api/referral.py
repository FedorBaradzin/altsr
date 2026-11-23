"""Кабинет реферала: статистика, реферальная ссылка, запрос выплаты."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.service import current_user
from ..config import Settings, get_settings
from ..db import get_session
from ..models import ReferralPayout, User
from ..referral import service as referral_service

router = APIRouter(prefix="/api/referral", tags=["referral"])


def _referral_link(code: str | None, settings: Settings) -> str | None:
    if not code:
        return None
    return f"{settings.site_url.rstrip('/')}/?ref={code}"


@router.get("/me")
async def my_referral(
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    # Ленивая выдача кода существующим пользователям (созданным до реф-программы).
    await referral_service.ensure_code(session, user)
    await session.commit()
    data = await referral_service.stats(session, user)
    data["link"] = _referral_link(data.get("code"), settings)
    return data


@router.post("/payout")
async def request_payout(
    address: str | None = Body(default=None, embed=True),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    # Нельзя создать вторую заявку, пока есть необработанная (pending).
    pending = (
        await session.execute(
            select(ReferralPayout).where(
                ReferralPayout.referrer_id == user.id,
                ReferralPayout.status == "pending",
            )
        )
    ).scalar_one_or_none()
    if pending is not None:
        raise HTTPException(status_code=400, detail="Уже есть заявка на выплату в обработке")

    bal = await referral_service.balance(session, user.id)
    if bal <= 0:
        raise HTTPException(status_code=400, detail="Недостаточный баланс для выплаты")

    payout = ReferralPayout(
        referrer_id=user.id,
        amount_usd=bal,
        status="pending",
        address=address,
        created_at=datetime.now(timezone.utc),
    )
    session.add(payout)
    await session.commit()
    return {
        "ok": True,
        "payout_id": payout.id,
        "amount_usd": payout.amount_usd,
        "status": payout.status,
    }
