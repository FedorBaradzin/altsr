"""«Где и как купить монету»: торговые площадки + прямые ссылки.

build_buy_options — чистая функция: из полей токена строит детерминированные ссылки
(swap / график / эксплорер). fetch_dex_venues — опциональное live-обогащение списком
реальных DEX-пар из DexScreener.

Это ИНФОРМАЦИЯ о том, где торгуется токен и как совершить своп, а не призыв покупать.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..discovery.base import HttpClient, to_float

logger = logging.getLogger("altsr.signals.venues")

# chain → имя сети в GeckoTerminal (для ссылки на пул).
GECKO_NET = {
    "ethereum": "eth", "base": "base", "bsc": "bsc", "solana": "solana",
    "polygon": "polygon_pos", "arbitrum": "arbitrum", "optimism": "optimism",
}

EXPLORER = {
    "ethereum": "https://etherscan.io/token/{a}",
    "base": "https://basescan.org/token/{a}",
    "bsc": "https://bscscan.com/token/{a}",
    "polygon": "https://polygonscan.com/token/{a}",
    "arbitrum": "https://arbiscan.io/token/{a}",
    "optimism": "https://optimistic.etherscan.io/token/{a}",
    "solana": "https://solscan.io/token/{a}",
}


@dataclass
class BuyOption:
    type: str          # swap | chart | explorer
    name: str          # человекочитаемое имя площадки/ссылки
    url: str
    note: str = ""     # напр. ликвидность/quote

    def as_dict(self) -> dict[str, Any]:
        d = {"type": self.type, "name": self.name, "url": self.url}
        if self.note:
            d["note"] = self.note
        return d


def _swap_option(chain: str, address: str) -> BuyOption | None:
    if chain == "solana":
        return BuyOption("swap", "Jupiter", f"https://jup.ag/swap/SOL-{address}")
    if chain == "bsc":
        return BuyOption("swap", "PancakeSwap",
                        f"https://pancakeswap.finance/swap?outputCurrency={address}")
    uni_chain = {"ethereum": "mainnet", "base": "base", "polygon": "polygon",
                 "arbitrum": "arbitrum", "optimism": "optimism"}.get(chain)
    if uni_chain:
        return BuyOption("swap", "Uniswap",
                        f"https://app.uniswap.org/swap?outputCurrency={address}&chain={uni_chain}")
    return None


def build_buy_options(chain: str, address: str, pair_address: str | None = None) -> list[BuyOption]:
    """Детерминированные ссылки «как купить» без обращения к сети."""
    opts: list[BuyOption] = []
    swap = _swap_option(chain, address)
    if swap:
        opts.append(swap)

    # График/пара на DexScreener.
    ds_target = pair_address or address
    opts.append(BuyOption("chart", "DexScreener",
                         f"https://dexscreener.com/{chain}/{ds_target}"))

    # GeckoTerminal пул (если знаем пару).
    net = GECKO_NET.get(chain)
    if net and pair_address:
        opts.append(BuyOption("chart", "GeckoTerminal",
                             f"https://www.geckoterminal.com/{net}/pools/{pair_address}"))

    # Эксплорер — проверить контракт.
    exp = EXPLORER.get(chain)
    if exp:
        opts.append(BuyOption("explorer", "Explorer", exp.format(a=address)))

    return opts


async def fetch_dex_venues(http: HttpClient, base_url: str, address: str) -> list[BuyOption]:
    """Live-список DEX-площадок, где торгуется токен (DexScreener tokens endpoint)."""
    url = f"{base_url}/latest/dex/tokens/{address}"
    payload = await http.get_json(url)
    pairs = (payload or {}).get("pairs") or []
    venues: list[BuyOption] = []
    seen: set[str] = set()
    # Сортируем по ликвидности убыв.
    pairs = sorted(pairs, key=lambda p: to_float((p.get("liquidity") or {}).get("usd")) or 0,
                   reverse=True)
    for p in pairs[:10]:
        dex = p.get("dexId") or "dex"
        quote = (p.get("quoteToken") or {}).get("symbol") or ""
        key = f"{dex}:{quote}"
        if key in seen:
            continue
        seen.add(key)
        liq = to_float((p.get("liquidity") or {}).get("usd"))
        note = f"{quote} · ликв. ${liq:,.0f}" if liq else quote
        if p.get("url"):
            venues.append(BuyOption("swap", dex.capitalize(), p["url"], note))
    return venues
