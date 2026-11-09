"""Проверка Telegram Login Widget.

Алгоритм Telegram: secret_key = SHA256(bot_token); проверяем HMAC-SHA256 от
data_check_string (поля кроме hash, отсортированы, 'k=v' через \\n) с этим ключом.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any


def verify_telegram_login(data: dict[str, Any], bot_token: str, max_age_sec: int = 86400) -> bool:
    if not bot_token or "hash" not in data:
        return False
    received = str(data["hash"])
    pairs = [f"{k}={data[k]}" for k in sorted(data) if k != "hash"]
    check_string = "\n".join(pairs)
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    expected = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        return False
    # Защита от повторного использования старых данных.
    try:
        if time.time() - int(data.get("auth_date", 0)) > max_age_sec:
            return False
    except (ValueError, TypeError):
        return False
    return True
