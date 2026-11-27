"""Воркер safety_screen: берёт неоскоренные токены → скринит → пишет отчёт → шина."""
from __future__ import annotations

import asyncio
import json
import logging

from ..config import Settings, get_settings
from ..db import get_sessionmaker
from ..discovery.base import HttpClient
from .screener import (
    screen_token,
    stale_review_tokens,
    store_result,
    unscored_tokens,
)

logger = logging.getLogger("altsr.safety.runner")

PUBSUB_CHANNEL = "altsr:safety"


async def screen_batch(settings: Settings, redis=None) -> int:
    async with get_sessionmaker()() as session:
        tokens = await unscored_tokens(session, settings.screen_batch_size)
        # Добираем пере-скринингом давних REVIEW-токенов: «мало данных» → настоящий
        # вердикт. Так радар начинает ловить скам, а не висеть в REVIEW. Нет пересечения
        # с unscored (у тех нет отчёта, у этих есть REVIEW).
        if settings.screen_rescreen_per_cycle > 0:
            tokens = tokens + await stale_review_tokens(
                session, settings.screen_rescreen_per_cycle
            )
        if not tokens:
            return 0

        # max_retries=1: RugCheck на мультах часто отдаёт 400, а GoPlus под лимитом —
        # HTTP-200 с кодом 4029 в теле; ретраи тут только жгут backoff и тормозят батч.
        async with HttpClient(
            timeout=settings.http_timeout_seconds,
            max_retries=1,
        ) as http:
            done = 0
            for token in tokens:
                try:
                    # force_solana_rugcheck: даём Solana реальные данные (authority / rugged /
                    # LP-lock / концентрация) — GoPlus(solana) под лимитом пуст.
                    result = await screen_token(
                        http, settings, token.chain, token.address,
                        force_solana_rugcheck=True,
                    )
                    report = await store_result(session, token, result)
                    done += 1
                    if redis is not None:
                        payload = json.dumps(
                            {
                                "token_id": token.id,
                                "chain": token.chain,
                                "address": token.address,
                                "verdict": report.verdict,
                                "risk_score": report.risk_score,
                            },
                            ensure_ascii=False,
                        )
                        try:
                            await redis.publish(PUBSUB_CHANNEL, payload)
                        except Exception as exc:  # noqa: BLE001
                            logger.warning("publish safety не удался: %s", exc)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("скрининг %s:%s упал: %s", token.chain, token.address, exc)
            return done


async def run_forever(settings: Settings | None = None, redis=None) -> None:
    settings = settings or get_settings()
    logger.info("Safety-воркер стартовал: батч %d, интервал %ds",
                settings.screen_batch_size, settings.screen_interval_seconds)
    while True:
        try:
            n = await screen_batch(settings, redis=redis)
            if n:
                logger.info("Оскорено токенов: %d", n)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Ошибка в safety-тике: %s", exc)
        await asyncio.sleep(settings.screen_interval_seconds)
