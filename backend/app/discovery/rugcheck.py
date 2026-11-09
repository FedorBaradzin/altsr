"""RugCheck — новые Solana-минты. Эндпоинт: GET {base}/stats/new_tokens

В Фазе 0 используется только как источник discovery (минты + базовые метаданные).
Полный risk-разбор RugCheck подключается в Фазе 1 (safety_screen).
"""
from __future__ import annotations

import logging
from typing import Any

from .base import HttpClient, NormalizedToken, parse_ts, to_float

logger = logging.getLogger("altsr.discovery.rugcheck")


def normalize_mint(item: dict) -> NormalizedToken | None:
    mint = item.get("mint") or item.get("address")
    if not mint:
        return None

    socials: dict[str, Any] = {}
    meta = item.get("metadata") or item.get("fileMeta") or {}
    for key in ("twitter", "telegram", "website", "discord"):
        val = item.get(key) or meta.get(key)
        if val:
            socials[key] = val

    return NormalizedToken(
        chain="solana",
        address=mint,
        source="rugcheck",
        symbol=item.get("symbol") or meta.get("symbol"),
        name=item.get("name") or meta.get("name"),
        created_at=parse_ts(item.get("createAt") or item.get("created_at")),
        liquidity_usd=to_float(item.get("liquidity") or item.get("totalMarketLiquidity")),
        fdv=to_float(item.get("fdv") or item.get("marketCap")),
        pair_address=None,
        dex=item.get("market") or None,
        socials=socials,
    )


async def fetch_new_tokens(http: HttpClient, base_url: str) -> list[NormalizedToken]:
    url = f"{base_url}/stats/new_tokens"
    payload = await http.get_json(url)
    # RugCheck отдаёт либо список, либо {"tokens": [...]}.
    rows = payload if isinstance(payload, list) else (payload or {}).get("tokens", [])
    results = [t for row in rows if (t := normalize_mint(row)) and t.is_valid]
    logger.info("RugCheck: %d новых Solana-минтов", len(results))
    return results
