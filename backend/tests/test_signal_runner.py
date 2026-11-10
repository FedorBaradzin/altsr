"""Signal runner end-to-end: PASS-токен → сигнал с venues → БД → API, дедуп."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport
from sqlalchemy import select

from app.config import get_settings
from app.db import create_all, get_sessionmaker
from app.discovery.base import NormalizedToken
from app.discovery.dedup import upsert_tokens
from app.models import SafetyReport, Signal


async def _seed_pass_token(liquidity=8000.0, verdict="PASS", risk=10):
    async with get_sessionmaker()() as s:
        res = await upsert_tokens(s, [
            NormalizedToken(chain="ethereum", address="0xtokenabc", source="t",
                            symbol="PEPE2", liquidity_usd=liquidity, pair_address="0xpair")
        ])
        token = res.inserted[0]
        s.add(SafetyReport(
            token_id=token.id, chain="ethereum", address="0xtokenabc",
            risk_score=risk, verdict=verdict, red_flags="[]", findings="{}",
            sources="goplus", created_at=datetime.now(timezone.utc),
        ))
        await s.commit()
        return token.id


async def test_signal_created_with_venues_and_dedup():
    from app.signals.runner import run_batch

    await create_all()
    await _seed_pass_token()
    settings = get_settings()
    settings.momentum_enabled = False  # тест о venues/дедупе, не о моментуме (без live-данных)

    created = await run_batch(settings)  # notifier без конфига → no-op
    assert created == 1

    async with get_sessionmaker()() as s:
        sig = (await s.execute(select(Signal))).scalar_one()
        assert sig.side == "BUY"
        assert sig.confidence > 0
        assert "Jupiter" in sig.venues or "Uniswap" in sig.venues
        assert "safety PASS" in sig.reasons

    # Повторный прогон не плодит сигналы.
    assert await run_batch(settings) == 0


async def test_review_token_gets_no_signal():
    from app.signals.runner import run_batch

    await create_all()
    await _seed_pass_token(verdict="REVIEW")
    assert await run_batch(get_settings()) == 0


@pytest.fixture
async def client():
    from app.main import app

    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def test_api_signals_and_venues(client):
    from app.signals.runner import run_batch

    token_id = await _seed_pass_token()
    s = get_settings()
    s.momentum_enabled = False  # тест об API/venues, не о моментуме (без live-данных)
    await run_batch(s)

    r = await client.get("/api/signals")
    body = r.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["side"] == "BUY"
    assert item["symbol"] == "PEPE2"
    assert len(item["venues"]) >= 1

    # Лента токенов показывает уверенность сигнала.
    tr = await client.get("/api/tokens")
    assert tr.json()["items"][0]["signal_confidence"] is not None

    # Эндпоинт venues (детерминированные ссылки, без live).
    vr = await client.get(f"/api/tokens/{token_id}/venues")
    assert vr.status_code == 200
    names = {o["name"] for o in vr.json()["options"]}
    assert "Uniswap" in names and "DexScreener" in names
