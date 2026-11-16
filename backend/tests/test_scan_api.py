"""On-demand скам-чек /api/scan: валидация, кэш, rate-limit, формат ответа.

screen_token замокан — сеть не трогаем, проверяем только логику эндпоинта.
"""
from __future__ import annotations

import httpx
import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport

from app.api import scan as scan_mod
from app.safety.base import RedFlag, SafetyFindings, SafetyResult

# Реальный валидный USDC (ethereum) — формат проходит валидацию адреса.
USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
# Реальный валидный минт (Solana, USDC) — формат проходит валидацию.
SOL_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


@pytest.fixture
async def client():
    from app.main import app
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.fixture(autouse=True)
def _reset_state():
    """Глобальные кэш и rate-limit — чистим между тестами."""
    scan_mod._cache.clear()
    scan_mod._hits.clear()
    yield
    scan_mod._cache.clear()
    scan_mod._hits.clear()


def _fake_result(chain=" evm", address=USDC, verdict="PASS", risk=10, flags=None):
    f = SafetyFindings(
        chain="ethereum", address=address,
        is_honeypot=False, sell_tax=0.0, mint_authority_active=False,
        top_holder_pct=0.1, lp_locked=True, sources=["goplus"],
    )
    return SafetyResult(
        chain="ethereum", address=address, risk_score=risk, verdict=verdict,
        red_flags=flags or [], findings=f,
    )


def _patch_screen(monkeypatch, result=None, counter=None, calls=None):
    async def fake(http, settings, chain, address, **kw):
        if counter is not None:
            counter.append((chain, address))
        if calls is not None:
            calls.append({"chain": chain, "address": address, "kw": kw})
        return result or _fake_result(address=address)
    monkeypatch.setattr(scan_mod, "screen_token", fake)


async def test_unsupported_chain_422(client):
    r = await client.post("/api/scan", json={"chain": "dogechain", "address": USDC})
    assert r.status_code == 422


async def test_bad_evm_address_422(client, monkeypatch):
    _patch_screen(monkeypatch)
    r = await client.post("/api/scan", json={"chain": "ethereum", "address": "0xdeadbeef"})
    assert r.status_code == 422
    assert "дрес" in r.json()["detail"]  # «адрес»


async def test_bad_solana_address_422(client, monkeypatch):
    _patch_screen(monkeypatch)
    # содержит 0 и O — недопустимо в base58
    r = await client.post("/api/scan", json={"chain": "solana", "address": "0OO" + "1" * 30})
    assert r.status_code == 422


async def test_valid_evm_scan_returns_verdict(client, monkeypatch):
    flags = [RedFlag("few_holders", "soft", "Мало холдеров: 12", 10)]
    _patch_screen(monkeypatch, result=_fake_result(verdict="REVIEW", risk=40, flags=flags))
    r = await client.post("/api/scan", json={"chain": "ethereum", "address": USDC})
    assert r.status_code == 200
    j = r.json()
    assert j["verdict"] == "REVIEW"
    assert j["risk_score"] == 40
    assert j["is_malicious"] is False
    assert j["red_flags"][0]["code"] == "few_holders"
    assert j["checked"]["honeypot"] is True
    assert j["cached"] is False
    assert "disclaimer" in j and j["disclaimer"]


async def test_valid_solana_scan(client, monkeypatch):
    _patch_screen(monkeypatch)
    r = await client.post("/api/scan", json={"chain": "solana", "address": SOL_MINT})
    assert r.status_code == 200
    assert r.json()["verdict"] == "PASS"


async def test_second_call_is_cached(client, monkeypatch):
    calls: list = []
    _patch_screen(monkeypatch, counter=calls)
    body = {"chain": "ethereum", "address": USDC}
    r1 = await client.post("/api/scan", json=body)
    r2 = await client.post("/api/scan", json=body)
    assert r1.status_code == r2.status_code == 200
    assert r1.json()["cached"] is False
    assert r2.json()["cached"] is True
    assert len(calls) == 1  # второй раз провайдеров не дёргали


async def test_malicious_verdict_flagged(client, monkeypatch):
    flags = [RedFlag("honeypot", "hard", "Ханипот: продажа невозможна")]
    _patch_screen(monkeypatch, result=_fake_result(verdict="BLOCK", risk=95, flags=flags))
    r = await client.post("/api/scan", json={"chain": "bsc", "address": USDC})
    assert r.status_code == 200
    j = r.json()
    assert j["verdict"] == "BLOCK"
    assert j["is_malicious"] is True


async def test_rate_limit_429(client, monkeypatch):
    _patch_screen(monkeypatch)
    # разные адреса, чтобы кэш не скрыл лимит; один IP (ASGITransport → testclient)
    last = None
    for i in range(scan_mod._RL_MAX + 3):
        addr = "0x" + f"{i:040x}"
        last = await client.post("/api/scan", json={"chain": "ethereum", "address": addr})
    assert last.status_code == 429
    assert "роверок" in last.json()["detail"]  # «проверок»


async def test_provider_failure_502(client, monkeypatch):
    async def boom(http, settings, chain, address, **kw):
        raise RuntimeError("provider down")
    monkeypatch.setattr(scan_mod, "screen_token", boom)
    r = await client.post("/api/scan", json={"chain": "ethereum", "address": USDC})
    assert r.status_code == 502


async def test_solana_forces_rugcheck(client, monkeypatch):
    # on-demand Solana scan must force RugCheck (GoPlus-solana is rate-limited)
    calls = []
    _patch_screen(monkeypatch, result=_fake_result(verdict="PASS"), calls=calls)
    r = await client.post("/api/scan", json={"chain": "solana", "address": SOL_MINT})
    assert r.status_code == 200
    assert calls and calls[0]["kw"].get("force_solana_rugcheck") is True
