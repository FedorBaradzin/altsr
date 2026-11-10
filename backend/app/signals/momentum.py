"""Моментум из DexScreener — чтобы входить только в РАСТУЩИЕ токены.

DexScreener бесплатный, без ключа (300 req/min). Один запрос
`GET /latest/dex/tokens/{address}` отдаёт по каждой паре:
priceChange m5/h1/h6/h24, volume m5/h1/h6/h24, txns.*.buys/sells, liquidity.
Берём пару с наибольшей ликвидностью (предпочтительно нужной сети).

Падение провайдера не роняет скрининг: возвращаем None, решает движок.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ..discovery.base import HttpClient

logger = logging.getLogger("altsr.signals.momentum")


@dataclass
class Momentum:
    price_change_m5: float | None = None   # проценты, напр. +36.4
    price_change_h1: float | None = None
    vol_h1: float | None = None            # USD
    vol_h6: float | None = None
    buys_m5: int | None = None
    sells_m5: int | None = None
    buys_h1: int | None = None
    sells_h1: int | None = None


def _f(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _liq(p: dict) -> float:
    return _f((p.get("liquidity") or {}).get("usd")) or 0.0


async def fetch_momentum(
    http: HttpClient, base_url: str, chain: str, address: str
) -> Momentum | None:
    url = f"{base_url}/latest/dex/tokens/{address}"
    data = await http.get_json(url)
    if not isinstance(data, dict):
        return None
    pairs = data.get("pairs") or []
    if not pairs:
        return None
    same = [p for p in pairs if (p.get("chainId") or "").lower() == chain.lower()]
    pool = max(same or pairs, key=_liq)

    pc = pool.get("priceChange") or {}
    vol = pool.get("volume") or {}
    tx = pool.get("txns") or {}
    m5 = tx.get("m5") or {}
    h1 = tx.get("h1") or {}
    return Momentum(
        price_change_m5=_f(pc.get("m5")),
        price_change_h1=_f(pc.get("h1")),
        vol_h1=_f(vol.get("h1")),
        vol_h6=_f(vol.get("h6")),
        buys_m5=_i(m5.get("buys")),
        sells_m5=_i(m5.get("sells")),
        buys_h1=_i(h1.get("buys")),
        sells_h1=_i(h1.get("sells")),
    )
