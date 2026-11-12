"""Личная привязка Telegram и алерты.

Поток: фронт запрашивает /link → получает deep-link t.me/<bot>?start=<code> →
пользователь жмёт Start → Telegram шлёт update на /webhook → сохраняем chat_id.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.service import current_user
from ..config import Settings, get_settings
from ..db import get_session
from ..models import TelegramLinkCode, User
from ..notify.telegram import send_to_chat, tg_get_username

router = APIRouter(prefix="/api/telegram", tags=["telegram"])

CODE_TTL_MIN = 15
_bot_username: str | None = None  # кэш @username бота для deep-link


def webhook_secret(settings: Settings) -> str:
    return hashlib.sha256(("tgwh:" + settings.jwt_secret).encode()).hexdigest()[:32]


async def _bot_name(settings: Settings) -> str | None:
    global _bot_username
    if _bot_username is None:
        _bot_username = await tg_get_username(settings)
    return _bot_username


@router.get("/status")
async def status(user: User = Depends(current_user)) -> dict:
    return {"linked": bool(user.tg_chat_id)}


@router.post("/link")
async def link(
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    if not settings.telegram_bot_token:
        raise HTTPException(status_code=503, detail="Telegram-бот не настроен")
    uname = await _bot_name(settings)
    if not uname:
        raise HTTPException(status_code=503, detail="Бот недоступен")
    # один активный код на пользователя
    await session.execute(delete(TelegramLinkCode).where(TelegramLinkCode.user_id == user.id))
    code = secrets.token_urlsafe(9)[:16]
    session.add(TelegramLinkCode(code=code, user_id=user.id))
    await session.commit()
    return {"url": f"https://t.me/{uname}?start={code}", "code": code, "bot": uname}


@router.post("/unlink")
async def unlink(
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    user.tg_chat_id = None
    await session.commit()
    return {"linked": False}


@router.post("/test")
async def test_alert(
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    if not user.tg_chat_id:
        raise HTTPException(status_code=400, detail="Telegram не привязан")
    ok = await send_to_chat(
        settings, user.tg_chat_id,
        "🔔 <b>ALTSR</b>\nТестовый алерт. Личные сигналы будут приходить сюда.",
    )
    return {"sent": ok}


@router.post("/webhook")
async def webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    if x_telegram_bot_api_secret_token != webhook_secret(settings):
        raise HTTPException(status_code=403, detail="bad secret")
    update = await request.json()
    msg = (update or {}).get("message") or {}
    text = (msg.get("text") or "").strip()
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    if not chat_id or not text.startswith("/start"):
        return {"ok": True}
    parts = text.split(maxsplit=1)
    code = parts[1].strip() if len(parts) > 1 else ""
    if not code:
        await send_to_chat(settings, str(chat_id),
                           "Откройте привязку из кабинета ALTSR, чтобы связать аккаунт.")
        return {"ok": True}
    row = (
        await session.execute(
            select(TelegramLinkCode).where(TelegramLinkCode.code == code)
        )
    ).scalar_one_or_none()
    if row is None:
        await send_to_chat(settings, str(chat_id), "Код привязки не найден или устарел.")
        return {"ok": True}
    created = row.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    if created < datetime.now(timezone.utc) - timedelta(minutes=CODE_TTL_MIN):
        await session.execute(delete(TelegramLinkCode).where(TelegramLinkCode.code == code))
        await session.commit()
        await send_to_chat(
            settings, str(chat_id), "Код привязки устарел. Сгенерируйте новый в кабинете."
        )
        return {"ok": True}
    user = (
        await session.execute(select(User).where(User.id == row.user_id))
    ).scalar_one_or_none()
    if user is not None:
        user.tg_chat_id = str(chat_id)
        await session.execute(delete(TelegramLinkCode).where(TelegramLinkCode.user_id == user.id))
        await session.commit()
        await send_to_chat(
            settings, str(chat_id),
            "✅ <b>ALTSR подключён</b>\nЛичные сигналы и алерты будут приходить сюда.",
        )
    return {"ok": True}
