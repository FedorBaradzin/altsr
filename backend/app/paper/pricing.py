"""Прайс-фид для бумажных позиций (DexScreener). Возвращает цену в USD или None."""
from __future__ import annotations

import logging

from ..discovery.base import HttpClient, to_float

logger = logging.getLogger("altsr.paper.pricing")


async def fetch_price_usd(http: HttpClient, base_url: str, address: str) -> float | None:
    """Текущая цена токена в USD — по самой ликвидной паре из DexScreener."""
    url = f"{base_url}/latest/dex/tokens/{address}"
    payload = await http.get_json(url)
    pairs = (payload or {}).get("pairs") or []
    best_price: float | None = None
    best_liq = -1.0
    for p in pairs:
        liq = to_float((p.get("liquidity") or {}).get("usd")) or 0.0
        price = to_float(p.get("priceUsd"))
        if price is not None and liq > best_liq:
            best_liq = liq
            best_price = price
    return best_price
