"""fetch_top_pools: тянет ТОП-пулы по объёму и помечает source=geckoterminal_top."""
from __future__ import annotations

from app.discovery import geckoterminal as gt


class _FakeHttp:
    def __init__(self, payload):
        self._p = payload
        self.calls = []

    async def get_json(self, url, **kw):
        self.calls.append((url, kw))
        return self._p


def _payload():
    return {
        "data": [
            {
                "id": "eth_0xpool",
                "attributes": {
                    "name": "WOW / WETH",
                    "address": "0xpoolpair",
                    "reserve_in_usd": "250000",
                    "base_token_price_usd": "1.5",
                    "price_change_percentage": {"h24": "12.5"},
                },
                "relationships": {"base_token": {"data": {"id": "eth_0xbase"}}},
            }
        ],
        "included": [
            {
                "id": "eth_0xbase",
                "type": "token",
                "attributes": {
                    "address": "0xbase",
                    "symbol": "WOW",
                    "name": "Wow Token",
                },
            }
        ],
    }


async def test_fetch_top_pools_tags_source():
    http = _FakeHttp(_payload())
    toks = await gt.fetch_top_pools(http, "https://base", ["eth"], pages=1)
    assert len(toks) == 1
    t = toks[0]
    assert t.source == "geckoterminal_top"
    assert t.address == "0xbase"
    assert t.chain == "ethereum"
    assert t.liquidity_usd == 250000.0
    # бьёт в /pools с сортировкой по 24ч-объёму
    url, kw = http.calls[0]
    assert url.endswith("/networks/eth/pools")
    assert kw["params"]["sort"] == "h24_volume_usd_desc"


async def test_fetch_top_pools_empty_graceful():
    assert await gt.fetch_top_pools(_FakeHttp(None), "https://base", ["eth"]) == []
    assert await gt.fetch_top_pools(_FakeHttp({"data": []}), "https://base", ["eth"]) == []
