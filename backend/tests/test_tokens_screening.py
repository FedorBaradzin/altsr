"""Публичная лента: проверка до показа — BLOCK/скам не постим (как у Coinbase)."""
from __future__ import annotations

import json

import httpx
import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport

from app.db import get_sessionmaker
from app.discovery.base import NormalizedToken
from app.discovery.dedup import upsert_tokens
from app.models import SafetyReport


@pytest.fixture
async def client():
    from app.main import app

    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def _seed():
    async with get_sessionmaker()() as s:
        res = await upsert_tokens(s, [
            NormalizedToken(chain="bsc", address="0xpass", source="t", liquidity_usd=50000),
            NormalizedToken(chain="bsc", address="0xscam", source="t", liquidity_usd=50000),
        ])
        by_addr = {t.address: t for t in res.inserted}
        s.add(SafetyReport(token_id=by_addr["0xpass"].id, chain="bsc", address="0xpass",
                           risk_score=10, verdict="PASS", red_flags="[]", sources="goplus"))
        s.add(SafetyReport(
            token_id=by_addr["0xscam"].id, chain="bsc", address="0xscam",
            risk_score=90, verdict="BLOCK", sources="goplus",
            red_flags=json.dumps([{"code": "airdrop_scam", "severity": "hard",
                                   "message": "airdrop scam", "weight": 0}])))
        await s.commit()


async def test_blocked_scam_hidden_from_feed_by_default(client):
    await _seed()
    body = (await client.get("/api/tokens")).json()
    addrs = {i["address"] for i in body["items"]}
    assert "0xpass" in addrs
    assert "0xscam" not in addrs          # BLOCK/скам не показываем


async def test_include_blocked_shows_scam_with_malicious_flag(client):
    await _seed()
    body = (await client.get("/api/tokens", params={"include_blocked": "true"})).json()
    scam = next(i for i in body["items"] if i["address"] == "0xscam")
    assert scam["verdict"] == "BLOCK"
    assert scam["is_malicious"] is True


async def test_strict_mode_hides_unscreened(client):
    # include_pending=false → строгий режим «проверка до показа»: непроверенные скрыты.
    async with get_sessionmaker()() as s:
        await upsert_tokens(s, [
            NormalizedToken(chain="bsc", address="0xnew", source="t", liquidity_usd=50000)])
        await s.commit()
    default = (await client.get("/api/tokens")).json()
    strict = (await client.get("/api/tokens", params={"include_pending": "false"})).json()
    assert "0xnew" in {i["address"] for i in default["items"]}     # pending виден по умолчанию
    assert "0xnew" not in {i["address"] for i in strict["items"]}  # и скрыт в строгом режиме


async def test_safety_detail_exposes_is_malicious(client):
    await _seed()
    feed = (await client.get("/api/tokens", params={"include_blocked": "true"})).json()
    scam_id = next(i["id"] for i in feed["items"] if i["address"] == "0xscam")
    detail = (await client.get(f"/api/tokens/{scam_id}/safety")).json()
    assert detail["is_malicious"] is True
