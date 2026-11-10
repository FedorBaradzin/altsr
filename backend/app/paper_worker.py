"""Entrypoint paper-executor: python -m app.paper_worker"""
from __future__ import annotations

import asyncio
import logging

from .config import get_settings
from .db import create_all
from .paper.runner import run_forever
from .redis_client import make_redis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)


async def main() -> None:
    settings = get_settings()
    await create_all()
    redis = await make_redis()  # для чтения аварийной остановки (общей для воркеров)
    await run_forever(settings, redis=redis)


if __name__ == "__main__":
    asyncio.run(main())
