"""Screener end-to-end на фикстурах: источники → merge → scoring → БД → API."""
from __future__ import annotations

import httpx
import pytest
import respx
from asgi_lifespan import LifespanManager
from httpx import ASGITransport
from sqlalchemy import select

from app.config import get_settings
from app.db import create_all, get_sessionmaker
from app.discovery.base import HttpClient, NormalizedToken
from app.discovery.dedup import upsert_tokens
from app.models import SafetyReport
from app.safety.runner import screen_batch
from app.safety.screener import screen_token

from .conftest import load_fixture


def _mock_evm(router, settings):
    router.get(url__startswith=f"{settings.goplus_base_url}/token_security/").mock(
        return_value=httpx.Response(200, json=load_fixture("goplus_evm_clean.json"))
    )
    router.get(f"{settings.honeypot_base_url}/IsHoneypot").mock(
        return_value=httpx.Response(200, json=load_fixture("honeypot_is_clean.json"))
    )


async def test_screen_token_evm_merges_and_passes():
    settings = get_settings()
    with respx.mock(assert_all_called=False) as router:
        _mock_evm(router, settings)
        async with HttpClient() as http:
            result = await screen_token(http, settings, "ethereum", "0xtokenabc")
    assert result.verdict == "PASS"
    assert "goplus" in result.findings.sources
    assert "honeypot.is" in result.findings.sources


async def test_screen_token_solana():
    settings = get_settings()
    settings.rugcheck_enabled = True  # тест проверяет solana-путь c RugCheck (мок ниже)
    with respx.mock(assert_all_called=False) as router:
        router.get(url__startswith=f"{settings.goplus_base_url}/solana/token_security").mock(
            return_value=httpx.Response(200, json={"result": {}})
        )
        router.get(url__startswith=f"{settings.rugcheck_base_url}/tokens/").mock(
            return_value=httpx.Response(200, json=load_fixture("rugcheck_report_clean.json"))
        )
        async with HttpClient() as http:
            result = await screen_token(http, settings, "solana", "so11111solmintaaa")
    assert result.verdict == "PASS"
    assert result.findings.lp_locked is True


@respx.mock(assert_all_called=False)
async def test_screen_batch_persists_report(respx_mock):
    settings = get_settings()
    _mock_evm(respx_mock, settings)
    await create_all()

    async with get_sessionmaker()() as s:
        await upsert_tokens(s, [
            NormalizedToken(chain="ethereum", address="0xtokenabc", source="t")
        ])

    done = await screen_batch(settings)
    assert done == 1

    async with get_sessionmaker()() as s:
        report = (await s.execute(select(SafetyReport))).scalar_one()
        assert report.verdict == "PASS"
        assert report.sources and "goplus" in report.sources

    # Повторный батч не находит неоскоренных токенов.
    assert await screen_batch(settings) == 0


@pytest.fixture
async def client():
    from app.main import app

    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@respx.mock(assert_all_called=False)
async def test_api_exposes_verdict(client, respx_mock):
    settings = get_settings()
    _mock_evm(respx_mock, settings)

    async with get_sessionmaker()() as s:
        await upsert_tokens(s, [
            NormalizedToken(chain="ethereum", address="0xtokenabc", source="t")
        ])
    await screen_batch(settings)

    # Лента отдаёт вердикт.
    r = await client.get("/api/tokens")
    body = r.json()
    assert body["items"][0]["verdict"] == "PASS"

    # Фильтр по вердикту.
    r2 = await client.get("/api/tokens", params={"verdict": "PASS"})
    assert r2.json()["total"] == 1
    r3 = await client.get("/api/tokens", params={"verdict": "BLOCK"})
    assert r3.json()["total"] == 0

    # Полный отчёт.
    token_id = body["items"][0]["id"]
    r4 = await client.get(f"/api/tokens/{token_id}/safety")
    assert r4.status_code == 200
    assert r4.json()["verdict"] == "PASS"
    assert isinstance(r4.json()["flags"], list)
