"""Сессионные токены (JWT HS256, без внешних зависимостей).

Подписываем HMAC-SHA256. Храним user_id и exp. Проверка — постоянное сравнение подписи.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue_token(user_id: int, secret: str, ttl_hours: int) -> str:
    header = _b64e(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64e(json.dumps(
        {"sub": user_id, "exp": int(time.time()) + ttl_hours * 3600},
        separators=(",", ":"),
    ).encode())
    signing_input = f"{header}.{payload}".encode()
    sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64e(sig)}"


def verify_token(token: str, secret: str) -> int | None:
    """Вернуть user_id, если токен валиден и не истёк, иначе None."""
    try:
        header, payload, sig = token.split(".")
    except ValueError:
        return None
    signing_input = f"{header}.{payload}".encode()
    expected = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(_b64d(sig), expected):
        return None
    try:
        data = json.loads(_b64d(payload))
    except (ValueError, TypeError):
        return None
    if int(data.get("exp", 0)) < int(time.time()):
        return None
    sub = data.get("sub")
    return int(sub) if isinstance(sub, int) else None
