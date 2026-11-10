"""Воркер discovery: 24/7 поллинг источников → нормализация → дедуп → БД → шина.

Запускается как отдельный процесс (см. app/worker.py). Один тик собирает
токены со всех источников, идемпотентно пишет их и публикует новинки в Redis
pub/sub-канал, на который подписан WebSocket API.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

from ..config import Settings, get_settings
from ..db import get_sessionmaker
from ..notify.alerts import SystemAlerter
from . import birdeye, dexscreener, geckoterminal, rugcheck
from .base import HttpClient
from .dedup import upsert_tokens

logger = logging.getLogger("altsr.discovery.runner")

PUBSUB_CHANNEL = "altsr:new_tokens"
BIRDEYE_LAST_KEY = "altsr:birdeye:last_fetch"


async def _birdeye_due(redis, interval: int, now_ts: float) -> bool:
    """Пора ли снова опрашивать Birdeye. Без Redis или при interval<=0 — всегда да."""
    if redis is None or interval <= 0:
        return True
    try:
        raw = await redis.get(BIRDEYE_LAST_KEY)
    except Exception:  # noqa: BLE001 — троттлинг не должен ронять тик
        return True
    if not raw:
        return True
    try:
        last = float(raw.decode() if isinstance(raw, bytes) else raw)
    except (ValueError, TypeError, AttributeError):
        return True
    return (now_ts - last) >= interval


async def _mark_birdeye(redis, now_ts: float) -> None:
    if redis is None:
        return
    try:
        await redis.set(BIRDEYE_LAST_KEY, str(now_ts))
    except Exception:  # noqa: BLE001
        pass


async def _safe_birdeye(
    http: HttpClient, settings: Settings, alerter: SystemAlerter | None, redis=None
) -> list:
    """Birdeye с троттлингом (экономия CU) и перехватом исчерпания кредитов → алерт."""
    now_ts = time.time()
    if not await _birdeye_due(redis, settings.birdeye_interval_seconds, now_ts):
        return []
    await _mark_birdeye(redis, now_ts)  # отмечаем попытку сразу (и для ошибок — ждём интервал)
    try:
        return await birdeye.fetch_new_listings(
            http,
            base_url=settings.birdeye_base_url,
            api_key=settings.birdeye_api_key,
            chains=settings.birdeye_chain_list,
            limit=settings.birdeye_new_listing_limit,
        )
    except birdeye.BirdeyeError as exc:
        logger.warning("Birdeye недоступен: %s", exc)
        if exc.needs_topup and alerter is not None:
            await alerter.alert(
                "birdeye_credits",
                f"Birdeye требует внимания: {exc}. "
                "Проверь ключ или пополни счёт в кабинете Birdeye.",
                severity="error",
                http=http,
            )
        return []


async def collect_once(
    http: HttpClient, settings: Settings, *, alerter: SystemAlerter | None = None, redis=None
) -> list:
    """Один проход по всем источникам. Возвращает список NormalizedToken."""
    coros = [
        geckoterminal.fetch_new_pools(
            http, settings.gecko_base_url, settings.gecko_network_list
        ),
        rugcheck.fetch_new_tokens(http, settings.rugcheck_base_url),
        dexscreener.fetch_latest_profiles(http, settings.dexscreener_base_url),
    ]
    if settings.birdeye_active:
        coros.append(_safe_birdeye(http, settings, alerter, redis))

    results = await asyncio.gather(*coros, return_exceptions=True)
    tokens = []
    for res in results:
        if isinstance(res, Exception):
            logger.warning("Источник упал: %s", res)
            continue
        tokens.extend(res)
    return tokens


async def run_tick(settings: Settings, redis=None) -> int:
    """Собрать и сохранить. Возвращает число новых токенов."""
    alerter = SystemAlerter(settings, redis=redis)
    async with HttpClient(
        timeout=settings.http_timeout_seconds,
        max_retries=settings.http_max_retries,
    ) as http:
        tokens = await collect_once(http, settings, alerter=alerter, redis=redis)

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
    alerter = SystemAlerter(settings, redis=redis)
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
            # Системный алерт о поломке воркера (дедуп — раз в 30 мин на этот код).
            try:
                await alerter.alert(
                    "discovery_worker_error",
                    f"Сбой тика discovery: {type(exc).__name__}: {exc}",
                    severity="critical", dedup_seconds=1800,
                )
            except Exception:  # noqa: BLE001 — алерт не должен ронять воркер
                logger.exception("Не удалось отправить системный алерт")
        await asyncio.sleep(settings.poll_interval_seconds)
