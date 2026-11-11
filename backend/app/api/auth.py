"""Роуты аутентификации: wallet / google / telegram + /api/me."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import google as google_auth
from ..auth import telegram as tg_auth
from ..auth import wallet as wallet_auth
from ..auth.service import (
    current_user,
    effective_tier,
    get_or_create_user,
    is_admin,
    new_nonce,
    session_token,
    take_nonce,
)
from ..config import Settings, get_settings
from ..db import get_session
from ..discovery.base import HttpClient
from ..models import User
from ..schemas import AuthToken, NonceOut, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_out(u: User, settings: Settings | None = None) -> UserOut:
    return UserOut(id=u.id, auth_method=u.auth_method, email=u.email,
                   display_name=u.display_name, tier=effective_tier(u),
                   tier_expires_at=u.tier_expires_at,
                   is_admin=is_admin(u, settings) if settings else False)


# ---------- Wallet ----------
@router.post("/wallet/nonce", response_model=NonceOut)
async def wallet_nonce(address: str = Body(..., embed=True)) -> NonceOut:
    nonce = new_nonce(address)
    return NonceOut(address=address, message=wallet_auth.build_message(nonce))


@router.post("/wallet/verify", response_model=AuthToken)
async def wallet_verify(
    address: str = Body(...), signature: str = Body(...),
    session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings),
) -> AuthToken:
    nonce = take_nonce(address)
    if nonce is None:
        raise HTTPException(status_code=400, detail="Nonce истёк — запросите заново")
    if not wallet_auth.verify_eth_signature(address, wallet_auth.build_message(nonce), signature):
        raise HTTPException(status_code=401, detail="Подпись неверна")
    user = await get_or_create_user(session, "wallet", address.lower(),
                                    display_name=address[:6] + "…" + address[-4:])
    await session.commit()
    return AuthToken(token=session_token(user, settings), user=_user_out(user, settings))


# ---------- Telegram ----------
@router.post("/telegram/verify", response_model=AuthToken)
async def telegram_verify(
    data: dict = Body(...),
    session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings),
) -> AuthToken:
    if not tg_auth.verify_telegram_login(data, settings.telegram_bot_token):
        raise HTTPException(status_code=401, detail="Проверка Telegram не пройдена")
    parts = [data.get("first_name"), data.get("last_name")]
    name = " ".join(x for x in parts if x) or data.get("username")
    user = await get_or_create_user(session, "telegram", str(data["id"]), display_name=name)
    await session.commit()
    return AuthToken(token=session_token(user, settings), user=_user_out(user, settings))


# ---------- Google ----------
@router.get("/google/login")
async def google_login(settings: Settings = Depends(get_settings)) -> RedirectResponse:
    if not settings.google_client_id:
        raise HTTPException(status_code=503, detail="Google OAuth не настроен")
    return RedirectResponse(google_auth.auth_url(settings))


@router.get("/google/callback")
async def google_callback(
    code: str = Query(...),
    session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    async with HttpClient(timeout=settings.http_timeout_seconds) as http:
        profile = await google_auth.exchange_code(http, settings, code)
    if not profile:
        raise HTTPException(status_code=401, detail="Google-авторизация не удалась")
    user = await get_or_create_user(session, "google", profile["sub"],
                                    email=profile.get("email"), display_name=profile.get("name"))
    await session.commit()
    token = session_token(user, settings)
    # Браузерный поток: вернуть на фронт с токеном во фрагменте.
    return RedirectResponse(f"{settings.site_url.rstrip('/')}/radar#token={token}")


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user),
             settings: Settings = Depends(get_settings)) -> UserOut:
    return _user_out(user, settings)
