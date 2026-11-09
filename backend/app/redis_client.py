"""Фабрика Redis-клиента. Возвращает None, если Redis недоступен/не настроен."""
from __future__ import annotations

import logging

from .config import get_settings

logger = logging.getLogger("altsr.redis")


async def make_redis():
    try:
        import redis.asyncio as aioredis
    except ImportError:
        logger.warning("пакет redis не установлен — работаем без Redis")
        return None
    try:
        client = aioredis.from_url(
            get_settings().redis_url, encoding="utf-8", decode_responses=True
        )
        await client.ping()
        return client
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis недоступен (%s) — продолжаем без него", exc)
        return None
