"""Entrypoint paper-executor: python -m app.paper_worker"""
from __future__ import annotations

import asyncio
import logging

from .config import get_settings
from .db import create_all
from .paper.runner import run_forever

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)


async def main() -> None:
    settings = get_settings()
    await create_all()
    await run_forever(settings)


if __name__ == "__main__":
    asyncio.run(main())
