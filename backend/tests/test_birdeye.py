"""Birdeye new_listing как источник discovery + детекция исчерпания кредитов.

Ключ Birdeye берётся ТОЛЬКО из настроек (env/.env), в коде/тестах — заглушка.
При 401/402/429 источник сигнализирует needs_topup=True → системный алерт в TG.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from app.discovery.base import HttpClient
from app.discovery.birdeye import (
    BirdeyeError,
    fetch_new_listings,
    normalize_new_listing,
)

BASE = "https://public-api.birdeye.so"
LISTING_URL = f"{BASE}/defi/v2/tokens/new_listing"

_ITEM = {
    "address": "So1NewMint1111111111111111111111111111111",
    "symbol": "NEW",
    "name": "New Token",
    "decimals": 9,
    "liquidity": 42000.5,
    "liquidityAddedAt": "2026-11-10T11:00:00",
    "logoURI": "https://img/new.png",
}


def test_normalize_maps_core_fields():
    tok = normalize_new_listing(_ITEM, "solana")
    assert tok is not None
    assert tok.source == "birdeye"
    assert tok.chain == "solana"
    assert tok.address == _ITEM["address"].lower()
    assert tok.symbol == "NEW"
    assert tok.liquidity_usd == 42000.5
    assert tok.created_at is not None


def test_normalize_rejects_item_without_address():
    assert normalize_new_listing({"symbol": "X"}, "solana") is None


@respx.mock(assert_all_called=True)
async def test_fetch_returns_tokens(respx_mock):
    respx_mock.get(url__startswith=LISTING_URL).mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"items": [_ITEM]}})
    )
    async with HttpClient() as http:
        tokens = await fetch_new_listings(
            http, base_url=BASE, api_key="k-test", chains=["solana"]
        )
    assert len(tokens) == 1
    assert tokens[0].source == "birdeye"


@respx.mock(assert_all_called=True)
async def test_fetch_empty_items_ok(respx_mock):
    respx_mock.get(url__startswith=LISTING_URL).mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"items": []}})
    )
    async with HttpClient() as http:
        tokens = await fetch_new_listings(http, base_url=BASE, api_key="k", chains=["solana"])
    assert tokens == []


@respx.mock(assert_all_called=True)
async def test_fetch_sends_api_key_and_chain_headers(respx_mock):
    route = respx_mock.get(url__startswith=LISTING_URL).mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"items": []}})
    )
    async with HttpClient() as http:
        await fetch_new_listings(http, base_url=BASE, api_key="secret-key", chains=["solana"])
    req = route.calls.last.request
    assert req.headers.get("x-api-key") == "secret-key"
    assert req.headers.get("x-chain") == "solana"


@pytest.mark.parametrize("status", [401, 403])
@respx.mock(assert_all_called=True)
async def test_unauthorized_raises_topup(respx_mock, status):
    respx_mock.get(url__startswith=LISTING_URL).mock(return_value=httpx.Response(status))
    async with HttpClient(max_retries=1) as http:
        with pytest.raises(BirdeyeError) as ei:
            await fetch_new_listings(http, base_url=BASE, api_key="bad", chains=["solana"])
    assert ei.value.needs_topup is True


@pytest.mark.parametrize("status", [402, 429])
@respx.mock(assert_all_called=False)
async def test_payment_or_rate_limit_raises_topup(respx_mock, status):
    respx_mock.get(url__startswith=LISTING_URL).mock(return_value=httpx.Response(status))
    async with HttpClient(max_retries=1) as http:
        with pytest.raises(BirdeyeError) as ei:
            await fetch_new_listings(http, base_url=BASE, api_key="k", chains=["solana"])
    assert ei.value.needs_topup is True


@respx.mock(assert_all_called=True)
async def test_transient_5xx_returns_empty_not_topup(respx_mock):
    # 5xx — временная ошибка, НЕ повод слать «пополни счёт».
    respx_mock.get(url__startswith=LISTING_URL).mock(return_value=httpx.Response(503))
    async with HttpClient(max_retries=1) as http:
        tokens = await fetch_new_listings(http, base_url=BASE, api_key="k", chains=["solana"])
    assert tokens == []


class _CapturingAlerter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def alert(self, code, message, **_kw):
        self.calls.append((code, message))
        return True


@respx.mock(assert_all_called=False)
async def test_runner_fires_topup_alert_when_birdeye_401(respx_mock):
    """collect_once должен слать системный алерт при исчерпании кредитов Birdeye."""
    from app.config import get_settings
    from app.discovery.runner import collect_once

    s = get_settings()
    s.birdeye_enabled = True
    s.birdeye_api_key = "bad-key"
    object.__setattr__(s, "birdeye_chains", "solana")
    object.__setattr__(s, "gecko_networks", "eth")

    # Прочие источники отвечают пусто, Birdeye — 401.
    respx_mock.get(url__startswith=f"{s.gecko_base_url}/networks/").mock(
        return_value=httpx.Response(200, json={"data": [], "included": []})
    )
    respx_mock.get(f"{s.rugcheck_base_url}/stats/new_tokens").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx_mock.get(f"{s.dexscreener_base_url}/token-profiles/latest/v1").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx_mock.get(url__startswith=LISTING_URL).mock(return_value=httpx.Response(401))

    alerter = _CapturingAlerter()
    async with HttpClient(max_retries=1) as http:
        tokens = await collect_once(http, s, alerter=alerter)

    assert tokens == []
    assert any(code == "birdeye_credits" for code, _ in alerter.calls)
