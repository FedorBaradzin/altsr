"""REST-эндпоинты сигналов и «где купить» (venues)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_session
from ..discovery.base import HttpClient
from ..models import Signal, Token
from ..schemas import SignalList, SignalOut, VenuesOut
from ..signals.venues import build_buy_options, fetch_dex_venues

router = APIRouter(prefix="/api", tags=["signals"])


@router.get("/signals", response_model=SignalList)
async def list_signals(
    session: AsyncSession = Depends(get_session),
    chain: str | None = Query(default=None),
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> SignalList:
    where = []
    if chain:
        where.append(Signal.chain == chain.lower())
    if min_confidence is not None:
        where.append(Signal.confidence >= min_confidence)

    base = select(Signal, Token.symbol).join(Token, Token.id == Signal.token_id).where(*where)
    total = (
        await session.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        await session.execute(
            base.order_by(Signal.created_at.desc()).limit(limit).offset(offset)
        )
    ).all()
    items = [SignalOut.from_signal(sig, symbol) for sig, symbol in rows]
    return SignalList(items=items, total=total)


@router.get("/tokens/{token_id}/venues", response_model=VenuesOut)
async def token_venues(
    token_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    live: bool = Query(default=False, description="подтянуть live-список DEX из DexScreener"),
) -> VenuesOut:
    token = (
        await session.execute(select(Token).where(Token.id == token_id))
    ).scalar_one_or_none()
    if token is None:
        raise HTTPException(status_code=404, detail="Токен не найден")

    options = build_buy_options(token.chain, token.address, token.pair_address)

    if live:
        settings = get_settings()
        async with HttpClient(timeout=settings.http_timeout_seconds, max_retries=1) as http:
            try:
                live_venues = await fetch_dex_venues(
                    http, settings.dexscreener_base_url, token.address
                )
                options = live_venues + options
            except Exception:  # noqa: BLE001 — live-обогащение не критично
                pass

    return VenuesOut(
        chain=token.chain, address=token.address,
        options=[o.as_dict() for o in options],
    )
