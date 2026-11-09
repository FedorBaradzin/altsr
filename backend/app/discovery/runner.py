"""Воркер discovery: 24/7 поллинг источников → нормализация → дедуп → БД → шина.

Запускается как отдельный процесс (см. app/worker.py). Один тик собирает
токены со всех источников, идемпотентно пишет их и публикует новинки в Redis
pub/sub-канал, на который подписан WebSocket API.
"""
from __future__ import annotations

import asyncio
import json
import logging

from ..config import Settings, get_settings
from ..db import get_sessionmaker
from . import dexscreener, geckoterminal, rugcheck
from .base import HttpClient
from .dedup import upsert_tokens

logger = logging.getLogger("altsr.discovery.runner")

PUBSUB_CHANNEL = "altsr:new_tokens"


async def collect_once(http: HttpClient, settings: Settings) -> list:
    """Один проход по всем источникам. Возвращает список NormalizedToken."""
    results = await asyncio.gather(
        geckoterminal.fetch_new_pools(
            http, settings.gecko_base_url, settings.gecko_network_list
        ),
        rugcheck.fetch_new_tokens(http, settings.rugcheck_base_url),
        dexscreener.fetch_latest_profiles(http, settings.dexscreener_base_url),
        return_exceptions=True,
    )
    tokens = []
    for res in results:
        if isinstance(res, Exception):
            logger.warning("Источник упал: %s", res)
            continue
        tokens.extend(res)
    return tokens


async def run_tick(settings: Settings, redis=None) -> int:
    """Собрать и сохранить. Возвращает число новых токенов."""
    async with HttpClient(
        timeout=settings.http_timeout_seconds,
        max_retries=settings.http_max_retries,
    ) as http:
        tokens = await collect_once(http, settings)

    async with get_sessionmaker()() as session:
        result = await upsert_tokens(
            session, tokens, redis=redis, dedup_ttl=settings.dedup_ttl_seconds
        )

    # Публикуем новинки в шину для живой ленты.
    if redis is not None and result.inserted:
        for row in result.inserted:
            payload = json.dumps(
                {
                    "id": row.id,
                    "chain": row.chain,
                    "address": row.address,
                    "symbol": row.symbol,
                    "source": row.source,
                },
                ensure_ascii=False,
            )
            try:
                await redis.publish(PUBSUB_CHANNEL, payload)
            except Exception as exc:  # noqa: BLE001
                logger.warning("publish не удался: %s", exc)

    return result.inserted_count


async def run_forever(settings: Settings | None = None, redis=None) -> None:
    settings = settings or get_settings()
    logger.info(
        "Discovery-воркер стартовал: интервал %ds, сети %s",
        settings.poll_interval_seconds, settings.gecko_network_list,
    )
    while True:
        try:
            n = await run_tick(settings, redis=redis)
            logger.info("Тик завершён: +%d новых токенов", n)
        except Exception as exc:  # noqa: BLE001 — воркер не должен падать
            logger.exception("Ошибка в тике: %s", exc)
        await asyncio.sleep(settings.poll_interval_seconds)
