"""DexScreener — обогащение/дополнительный источник новых пар.

В Фазе 0 используется token-profiles/latest как лёгкий поток «свежих» токенов.
Эндпоинт: GET {base}/token-profiles/latest/v1  (без ключа).
"""
from __future__ import annotations

import logging
from typing import Any

from .base import HttpClient, NormalizedToken

logger = logging.getLogger("altsr.discovery.dexscreener")

CHAIN_ALIASES = {
    "ethereum": "ethereum",
    "eth": "ethereum",
    "base": "base",
    "bsc": "bsc",
    "solana": "solana",
    "polygon": "polygon",
    "arbitrum": "arbitrum",
}


def normalize_profile(item: dict) -> NormalizedToken | None:
    address = item.get("tokenAddress")
    chain = item.get("chainId")
    if not address or not chain:
        return None

    socials: dict[str, Any] = {}
    if item.get("url"):
        socials["dexscreener"] = item["url"]
    for link in item.get("links", []) or []:
        label = (link.get("type") or link.get("label") or "link").lower()
        if link.get("url"):
            socials[label] = link["url"]
    websites = item.get("websites")
    if websites:
        socials["websites"] = [w.get("url") for w in websites if w.get("url")]

    return NormalizedToken(
        chain=CHAIN_ALIASES.get(chain.lower(), chain.lower()),
        address=address,
        source="dexscreener",
        symbol=None,
        name=item.get("description", "")[:120] or None,
        socials=socials,
    )


async def fetch_latest_profiles(http: HttpClient, base_url: str) -> list[NormalizedToken]:
    url = f"{base_url}/token-profiles/latest/v1"
    payload = await http.get_json(url)
    rows = payload if isinstance(payload, list) else (payload or {}).get("items", [])
    results = [t for row in rows if (t := normalize_profile(row)) and t.is_valid]
    logger.info("DexScreener: %d профилей токенов", len(results))
    return results
