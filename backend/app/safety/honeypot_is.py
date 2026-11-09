"""honeypot.is (EVM) — симуляция buy/sell → SafetyFindings.

GET {base}/IsHoneypot?address={addr}&chainID={id}
Поля: honeypotResult.isHoneypot, simulationResult.buyTax/sellTax (проценты),
simulationSuccess, token.* . Покрывает EVM-сети.
"""
from __future__ import annotations

import logging
from typing import Any

from ..discovery.base import HttpClient
from .base import SafetyFindings

logger = logging.getLogger("altsr.safety.honeypot")

CHAIN_ID = {
    "ethereum": "1",
    "bsc": "56",
    "base": "8453",
    "polygon": "137",
    "arbitrum": "42161",
}


def _pct_to_frac(v: Any) -> float | None:
    # honeypot.is отдаёт налог в процентах (напр. 3.0 = 3%) → в долю.
    if v is None:
        return None
    try:
        return float(v) / 100.0
    except (ValueError, TypeError):
        return None


def parse(addr: str, data: dict) -> SafetyFindings:
    hp = data.get("honeypotResult") or {}
    sim = data.get("simulationResult") or {}
    return SafetyFindings(
        address=addr.lower(),
        is_honeypot=hp.get("isHoneypot") if isinstance(hp.get("isHoneypot"), bool) else None,
        buy_tax=_pct_to_frac(sim.get("buyTax")),
        sell_tax=_pct_to_frac(sim.get("sellTax")),
        sources=["honeypot.is"],
        raw={"honeypot.is": {"isHoneypot": hp.get("isHoneypot"),
                             "buyTax": sim.get("buyTax"), "sellTax": sim.get("sellTax")}},
    )


async def fetch(http: HttpClient, base_url: str, chain: str, address: str) -> SafetyFindings:
    chain_id = CHAIN_ID.get(chain)
    if not chain_id:
        return SafetyFindings(chain=chain, address=address)
    url = f"{base_url}/IsHoneypot"
    payload = await http.get_json(url, params={"address": address, "chainID": chain_id})
    if not isinstance(payload, dict):
        return SafetyFindings(chain=chain, address=address.lower())
    f = parse(address, payload)
    f.chain = chain
    return f
