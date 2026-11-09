"""Entrypoint discovery-воркера: python -m app.worker"""
from __future__ import annotations

import asyncio
import logging

from .config import get_settings
from .db import create_all
from .discovery.runner import run_forever
from .redis_client import make_redis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)


async def main() -> None:
    settings = get_settings()
    # На проде таблицы создаёт Alembic; create_all безопасен (IF NOT EXISTS).
    await create_all()
    redis = await make_redis()
    await run_forever(settings, redis=redis)


if __name__ == "__main__":
    asyncio.run(main())
