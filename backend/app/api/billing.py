"""Роуты биллинга: тарифы, checkout (NOWPayments), IPN-вебхук."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.service import current_user
from ..billing import nowpayments
from ..billing.tiers import TIERS, tier_price
from ..config import Settings, get_settings
from ..db import get_session
from ..discovery.base import HttpClient
from ..models import Payment, User
from ..schemas import CheckoutOut, TierInfo

logger = logging.getLogger("altsr.api.billing")
router = APIRouter(prefix="/api/billing", tags=["billing"])


@router.get("/tiers", response_model=list[TierInfo])
async def list_tiers() -> list[TierInfo]:
    return [TierInfo(id=k, name=v["name"], price_usd=float(v["price_usd"]), features=v["features"])
            for k, v in TIERS.items()]


@router.post("/checkout", response_model=CheckoutOut)
async def checkout(
    tier: str = Body(..., embed=True),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings),
) -> CheckoutOut:
    price = tier_price(tier)
    if price is None or price <= 0:
        raise HTTPException(status_code=400, detail="Неверный платный тариф")

    payment = Payment(user_id=user.id, tier=tier, provider="nowpayments",
                      amount_usd=price, status="waiting",
                      created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    session.add(payment)
    await session.flush()

    site = settings.site_url.rstrip("/")
    async with HttpClient(timeout=settings.http_timeout_seconds) as http:
        inv = await nowpayments.create_invoice(
            http, settings, tier=tier, price_usd=price, order_id=f"altsr-{payment.id}",
            success_url=f"{site}/app?paid=1", cancel_url=f"{site}/pricing",
            ipn_url=f"{site}/api/billing/ipn",
        )
    if inv:
        payment.invoice_id = inv.get("id")
    await session.commit()
    return CheckoutOut(invoice_url=inv.get("invoice_url") if inv else None,
                       payment_id=payment.id, tier=tier)


@router.post("/ipn")
async def ipn(
    request: Request,
    session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings),
) -> dict:
    raw = await request.body()
    sig = request.headers.get("x-nowpayments-sig")
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="bad body")

    if not nowpayments.verify_ipn(payload, sig, settings.nowpayments_ipn_secret):
        raise HTTPException(status_code=401, detail="bad signature")

    order_id = str(payload.get("order_id", ""))
    status = str(payload.get("payment_status", ""))
    pay_id = payload.get("payment_id")
    payment = None
    if order_id.startswith("altsr-"):
        payment = (
            await session.execute(select(Payment).where(Payment.id == int(order_id.split("-")[1])))
        ).scalar_one_or_none()
    if payment is None:
        return {"ok": True}  # не наш ордер — тихо подтверждаем приём

    payment.payment_id = str(pay_id) if pay_id else payment.payment_id
    payment.status = status
    payment.updated_at = datetime.now(timezone.utc)

    if status in nowpayments.PAID_STATES:
        user = (
            await session.execute(select(User).where(User.id == payment.user_id))
        ).scalar_one_or_none()
        if user is not None:
            user.tier = payment.tier
            base = max(user.tier_expires_at or datetime.now(timezone.utc),
                       datetime.now(timezone.utc))
            if base.tzinfo is None:
                base = base.replace(tzinfo=timezone.utc)
            user.tier_expires_at = base + timedelta(days=30)
            logger.info("Оплата подтверждена: user=%s tier=%s", user.id, payment.tier)
    await session.commit()
    return {"ok": True}
