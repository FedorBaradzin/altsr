"""Google OAuth2 (code flow). Обмен кода на токен + userinfo.

Сетевые вызовы вынесены в функции, которые легко мокать в тестах.
"""
from __future__ import annotations

import logging
from urllib.parse import urlencode

from ..config import Settings
from ..discovery.base import HttpClient

logger = logging.getLogger("altsr.auth.google")

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v3/userinfo"


def auth_url(s: Settings, state: str = "") -> str:
    params = {
        "client_id": s.google_client_id,
        "redirect_uri": s.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
    }
    if state:
        params["state"] = state
    return f"{AUTH_ENDPOINT}?{urlencode(params)}"


async def exchange_code(http: HttpClient, s: Settings, code: str) -> dict | None:
    """Обменять код на профиль: {sub, email, name} или None."""
    resp = await http.post(TOKEN_ENDPOINT, data={
        "code": code,
        "client_id": s.google_client_id,
        "client_secret": s.google_client_secret,
        "redirect_uri": s.google_redirect_uri,
        "grant_type": "authorization_code",
    })
    if resp is None or resp.status_code != 200:
        logger.warning("Google token exchange failed: %s", getattr(resp, "status_code", "none"))
        return None
    access = resp.json().get("access_token")
    if not access:
        return None
    info = await http.get_json(USERINFO_ENDPOINT, headers={"Authorization": f"Bearer {access}"})
    if not isinstance(info, dict) or not info.get("sub"):
        return None
    return {"sub": info["sub"], "email": info.get("email"), "name": info.get("name")}
