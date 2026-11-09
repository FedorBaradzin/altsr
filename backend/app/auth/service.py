"""Сессии, пользователи и зависимости доступа (гейтинг по тарифам)."""
from __future__ import annotations

import secrets
import time
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..db import get_session
from ..models import User
from .tokens import issue_token, verify_token

TIER_RANK = {"free": 0, "pro": 1, "trader": 2, "team": 3}

# Простой in-memory nonce-store для входа кошельком (на один инстанс).
# Для мульти-инстанса заменить на Redis.
_NONCES: dict[str, tuple[str, float]] = {}
_NONCE_TTL = 300.0


def new_nonce(address: str) -> str:
    nonce = secrets.token_hex(16)
    _NONCES[address.lower()] = (nonce, time.time() + _NONCE_TTL)
    return nonce


def take_nonce(address: str) -> str | None:
    """Вернуть и инвалидировать nonce (одноразовый)."""
    rec = _NONCES.pop(address.lower(), None)
    if not rec:
        return None
    nonce, exp = rec
    return nonce if exp >= time.time() else None


async def get_or_create_user(
    session: AsyncSession, auth_method: str, subject: str,
    *, email: str | None = None, display_name: str | None = None,
) -> User:
    user = (
        await session.execute(
            select(User).where(User.auth_method == auth_method, User.subject == subject)
        )
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if user is None:
        user = User(auth_method=auth_method, subject=subject, email=email,
                    display_name=display_name, tier="free", created_at=now, last_login_at=now)
        session.add(user)
    else:
        user.last_login_at = now
        if email and not user.email:
            user.email = email
    await session.flush()
    return user


def session_token(user: User, s: Settings) -> str:
    return issue_token(user.id, s.jwt_secret, s.session_ttl_hours)


def effective_tier(user: User) -> str:
    """Тариф с учётом срока. Истёкший платный → free."""
    if user.tier != "free" and user.tier_expires_at is not None:
        exp = user.tier_expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            return "free"
    return user.tier


async def optional_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> User | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    uid = verify_token(authorization.split(" ", 1)[1], settings.jwt_secret)
    if uid is None:
        return None
    return (await session.execute(select(User).where(User.id == uid))).scalar_one_or_none()


async def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Требуется вход")
    return user


def require_tier(min_tier: str):
    """Зависимость: доступ только с тарифом не ниже min_tier."""
    async def _dep(user: User = Depends(current_user)) -> User:
        if TIER_RANK.get(effective_tier(user), 0) < TIER_RANK.get(min_tier, 0):
            raise HTTPException(status_code=402, detail=f"Нужен тариф {min_tier}+")
        return user
    return _dep


def is_admin(user: User, s: Settings) -> bool:
    ids = s.admin_identifier_list
    if not ids:
        return False
    if (user.subject or "").lower() in ids:
        return True
    return bool(user.email and user.email.lower() in ids)


async def require_admin(
    user: User = Depends(current_user), settings: Settings = Depends(get_settings),
) -> User:
    if not is_admin(user, settings):
        raise HTTPException(status_code=403, detail="Только для администратора")
    return user
