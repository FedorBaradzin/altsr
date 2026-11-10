"""Воркер paper-executor: открыть по сигналам → вести позиции → выходы."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from ..config import Settings, get_settings
from ..db import get_sessionmaker
from ..discovery.base import HttpClient
from ..risk import killswitch_store
from .executor import open_from_signals, process_positions
from .pricing import fetch_price_usd

logger = logging.getLogger("altsr.paper.runner")


def _make_price_fn(http: HttpClient, settings: Settings):
    async def get_price(_chain: str, address: str) -> float | None:
        return await fetch_price_usd(http, settings.dexscreener_base_url, address)
    return get_price


async def run_tick(settings: Settings, redis=None) -> tuple[int, int]:
    now = datetime.now(timezone.utc)
    killswitch = await killswitch_store.get_state(redis)
    async with HttpClient(
        timeout=settings.http_timeout_seconds, max_retries=settings.http_max_retries
    ) as http:
        get_price = _make_price_fn(http, settings)
        async with get_sessionmaker()() as session:
            opened = await open_from_signals(session, settings, get_price, now, killswitch)
            closed = await process_positions(session, settings, get_price, now)
            await session.commit()
    return opened, closed


async def run_forever(settings: Settings | None = None, redis=None) -> None:
    settings = settings or get_settings()
    logger.info("Paper-executor стартовал: интервал %ds, старт-баланс $%.0f",
                settings.paper_interval_seconds, settings.paper_start_balance)
    while True:
        try:
            opened, closed = await run_tick(settings, redis=redis)
            if opened or closed:
                logger.info("Тик: открыто %d, закрыто %d", opened, closed)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Ошибка в paper-тике: %s", exc)
        await asyncio.sleep(settings.paper_interval_seconds)
