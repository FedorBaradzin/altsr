"""Батч прайс-фид DexScreener: выбор самой ликвидной пары + кэш."""
from __future__ import annotations

from app.paper import pricing


class _FakeHttp:
    def __init__(self, payload):
        self.payload = payload
        self.calls: list[str] = []

    async def get_json(self, url, **kw):
        self.calls.append(url)
        return self.payload


async def test_fetch_prices_picks_best_liquidity_and_keys_by_chain():
    pricing._PRICE_CACHE.clear()
    payload = {"pairs": [
        {"chainId": "base", "baseToken": {"address": "0xAAA"}, "priceUsd": "2.0", "liquidity": {"usd": 1000}},
        {"chainId": "base", "baseToken": {"address": "0xAAA"}, "priceUsd": "3.0", "liquidity": {"usd": 50000}},
        {"chainId": "bsc", "baseToken": {"address": "0xBBB"}, "priceUsd": "0.5", "liquidity": {"usd": 9000}},
    ]}
    http = _FakeHttp(payload)
    out = await pricing.fetch_prices_usd(http, "http://x", {("base", "0xAAA"), ("bsc", "0xBBB")})
    assert out[("base", "0xaaa")] == 3.0   # самая ликвидная пара выигрывает
    assert out[("bsc", "0xbbb")] == 0.5


async def test_fetch_prices_uses_cache_on_second_call():
    pricing._PRICE_CACHE.clear()
    http1 = _FakeHttp({"pairs": [
        {"chainId": "base", "baseToken": {"address": "0xAAA"}, "priceUsd": "2.0", "liquidity": {"usd": 1000}},
    ]})
    await pricing.fetch_prices_usd(http1, "http://x", {("base", "0xAAA")})
    http2 = _FakeHttp({"pairs": []})
    out = await pricing.fetch_prices_usd(http2, "http://x", {("base", "0xAAA")})
    assert out[("base", "0xaaa")] == 2.0
    assert http2.calls == []   # обслужено из кэша, без сетевого запроса


async def test_fetch_prices_missing_token_absent_from_result():
    pricing._PRICE_CACHE.clear()
    http = _FakeHttp({"pairs": []})
    out = await pricing.fetch_prices_usd(http, "http://x", {("base", "0xZZZ")})
    assert ("base", "0xzzz") not in out
