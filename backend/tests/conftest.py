"""Общие фикстуры. БД — sqlite in-memory, Redis — fakeredis."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

# Критично: задать тестовое окружение ДО первого get_settings().
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"

from app.config import get_settings  # noqa: E402
from app.db import create_all, get_sessionmaker, reset_engine_for_tests  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    reset_engine_for_tests()
    yield
    reset_engine_for_tests()


@pytest.fixture
async def session():
    await create_all()
    async with get_sessionmaker()() as s:
        yield s


@pytest.fixture
async def fake_redis():
    import fakeredis.aioredis

    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()
