"""GeckoTerminal new_pools — новые пулы по сетям (EVM + Solana), без ключа.

Эндпоинт: GET {base}/networks/{network}/new_pools
Docs-форма ответа — JSON:API (data[] + included[]).
"""
from __future__ import annotations

import logging
from typing import Any

from .base import HttpClient, NormalizedToken, parse_ts, to_float

logger = logging.getLogger("altsr.discovery.gecko")

# Имена сетей в GeckoTerminal → наши канонические chain-идентификаторы.
NETWORK_TO_CHAIN = {
    "eth": "ethereum",
    "ethereum": "ethereum",
    "base": "base",
    "bsc": "bsc",
    "polygon_pos": "polygon",
    "arbitrum": "arbitrum",
    "solana": "solana",
}


def _index_included(payload: dict) -> dict[str, dict]:
    """included[] → {id: attributes} для резолва base_token."""
    out: dict[str, dict] = {}
    for item in payload.get("included", []) or []:
        if isinstance(item, dict) and "id" in item:
            out[item["id"]] = item.get("attributes", {}) or {}
    return out


def normalize_pool(pool: dict, included: dict[str, dict], network: str) -> NormalizedToken | None:
    attrs = pool.get("attributes", {}) or {}
    rels = pool.get("relationships", {}) or {}

    base_ref = (((rels.get("base_token") or {}).get("data")) or {}).get("id")
    base_attrs = included.get(base_ref, {}) if base_ref else {}

    # Адрес базового токена; если included пуст — вытащим из id вида "eth_0x...".
    address = base_attrs.get("address")
    if not address and base_ref and "_" in base_ref:
        address = base_ref.split("_", 1)[1]
    if not address:
        return None

    dex_ref = (((rels.get("dex") or {}).get("data")) or {}).get("id")

    socials: dict[str, Any] = {}
    for key in ("websites", "twitter_handle", "telegram_handle", "discord_url"):
        val = base_attrs.get(key)
        if val:
            socials[key] = val

    chain = NETWORK_TO_CHAIN.get(network, network)
    return NormalizedToken(
        chain=chain,
        address=address,
        source="geckoterminal",
        symbol=base_attrs.get("symbol") or (attrs.get("name") or "").split(" / ")[0] or None,
        name=base_attrs.get("name") or attrs.get("name"),
        created_at=parse_ts(attrs.get("pool_created_at")),
        liquidity_usd=to_float(attrs.get("reserve_in_usd")),
        fdv=to_float(attrs.get("fdv_usd")),
        pair_address=attrs.get("address"),
        dex=dex_ref,
        socials=socials,
    )


async def fetch_new_pools(
    http: HttpClient, base_url: str, networks: list[str]
) -> list[NormalizedToken]:
    results: list[NormalizedToken] = []
    for network in networks:
        url = f"{base_url}/networks/{network}/new_pools"
        payload = await http.get_json(url, params={"include": "base_token,dex"})
        if not isinstance(payload, dict):
            continue
        included = _index_included(payload)
        for pool in payload.get("data", []) or []:
            tok = normalize_pool(pool, included, network)
            if tok and tok.is_valid:
                results.append(tok)
    logger.info("GeckoTerminal: %d токенов из %d сетей", len(results), len(networks))
    return results
