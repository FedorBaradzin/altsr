"""API: /health и /api/tokens (список + фильтры)."""
from __future__ import annotations

import httpx
import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport

from app.discovery.base import NormalizedToken
from app.discovery.dedup import upsert_tokens
from app.db import get_sessionmaker


@pytest.fixture
async def client():
    from app.main import app

    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_tokens_list_and_chain_filter(client):
    async with get_sessionmaker()() as s:
        await upsert_tokens(
            s,
            [
                NormalizedToken(chain="ethereum", address="0x1", source="t", liquidity_usd=5000),
                NormalizedToken(chain="solana", address="so2", source="t", liquidity_usd=100),
            ],
        )
    r = await client.get("/api/tokens")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2

    r2 = await client.get("/api/tokens", params={"chain": "solana"})
    assert r2.json()["total"] == 1
    assert r2.json()["items"][0]["chain"] == "solana"

    r3 = await client.get("/api/tokens", params={"min_liquidity": 1000})
    assert r3.json()["total"] == 1
    assert r3.json()["items"][0]["chain"] == "ethereum"
