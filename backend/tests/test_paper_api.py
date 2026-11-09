"""API бумажной симуляции: summary и positions."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport

from app.config import get_settings
from app.db import get_sessionmaker
from app.discovery.base import NormalizedToken
from app.discovery.dedup import upsert_tokens
from app.models import PaperPosition
from app.paper.executor import get_or_create_account


@pytest.fixture
async def client():
    from app.main import app

    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def test_summary_empty(client):
    r = await client.get("/api/paper/summary")
    assert r.status_code == 200
    body = r.json()
    s = get_settings()
    assert body["start_balance"] == s.paper_start_balance
    assert body["equity"] == s.paper_start_balance
    assert len(body["plan"]) == 5
    assert "прогноз" in body["disclaimer"].lower()


async def test_summary_and_positions_with_data(client):
    s = get_settings()
    now = datetime.now(timezone.utc)
    async with get_sessionmaker()() as sess:
        acc = await get_or_create_account(sess, s)
        acc.cash -= 100
        res = await upsert_tokens(sess, [
            NormalizedToken(chain="ethereum", address="0xwin", source="t", symbol="W")
        ])
        tid = res.inserted[0].id
        sess.add(PaperPosition(
            token_id=tid, chain="ethereum", address="0xwin", symbol="W", status="open",
            size_usd=100, entry_price=1.0, peak_price=1.5, last_price=1.4,
            remaining_fraction=1.0, realized_pnl_usd=0.0,
            opened_at=now, last_high_at=now,
        ))
        await sess.commit()

    r = await client.get("/api/paper/summary")
    body = r.json()
    assert body["open_positions"] == 1
    # Открытая позиция в плюсе → нереализованный P&L положительный.
    assert body["unrealized_pnl"] > 0

    rp = await client.get("/api/paper/positions", params={"status": "open"})
    pbody = rp.json()
    assert pbody["total"] == 1
    assert pbody["items"][0]["symbol"] == "W"
    assert pbody["items"][0]["current_value_usd"] > 100
