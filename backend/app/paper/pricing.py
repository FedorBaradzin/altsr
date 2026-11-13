"""Прайс-фид для бумажных позиций (DexScreener). Возвращает цену в USD или None."""
from __future__ import annotations

import logging
import time

from ..discovery.base import HttpClient, to_float

logger = logging.getLogger("altsr.paper.pricing")

# Ключ прайс-кэша: (chain_lower, address_lower) -> (price_usd, ts).
PriceKey = tuple[str, str]
_PRICE_CACHE: dict[PriceKey, tuple[float, float]] = {}
_PRICE_TTL = 60.0  # сек: ограничиваем частоту обращений к DexScreener
_BATCH = 30        # DexScreener tokens-эндпоинт принимает до 30 адресов за запрос


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


async def fetch_prices_usd(
    http: HttpClient, base_url: str, keys: set[PriceKey], *, ttl: float = _PRICE_TTL
) -> dict[PriceKey, float]:
    """Цены в USD для набора (chain, address). Батчами по 30 адресов, с кэшем.

    Возвращает только те ключи, для которых цена нашлась. Сетевые сбои не роняют
    вызов — отдаём что есть (из кэша/успешных батчей).
    """
    now = time.time()
    out: dict[PriceKey, float] = {}
    need: list[PriceKey] = []
    for chain, addr in keys:
        k = (chain.lower(), addr.lower())
        hit = _PRICE_CACHE.get(k)
        if hit and now - hit[1] < ttl:
            out[k] = hit[0]
        else:
            need.append(k)
    if not need:
        return out

    uniq_addrs = list({addr for _c, addr in need})
    for i in range(0, len(uniq_addrs), _BATCH):
        chunk = uniq_addrs[i : i + _BATCH]
        url = f"{base_url}/latest/dex/tokens/{','.join(chunk)}"
        try:
            payload = await http.get_json(url)
        except Exception as exc:  # noqa: BLE001 — прайс не должен ронять оценку счёта
            logger.warning("batch price fetch failed: %s", exc)
            continue
        best: dict[PriceKey, tuple[float, float]] = {}  # (chain,addr)->(price,liq)
        for p in (payload or {}).get("pairs") or []:
            cid = (p.get("chainId") or "").lower()
            base_addr = ((p.get("baseToken") or {}).get("address") or "").lower()
            if not cid or not base_addr:
                continue
            price = to_float(p.get("priceUsd"))
            if price is None:
                continue
            liq = to_float((p.get("liquidity") or {}).get("usd")) or 0.0
            kk = (cid, base_addr)
            if kk not in best or liq > best[kk][1]:
                best[kk] = (price, liq)
        for kk, (price, _liq) in best.items():
            _PRICE_CACHE[kk] = (price, now)

    for k in need:
        hit = _PRICE_CACHE.get(k)
        if hit and now - hit[1] < ttl:
            out[k] = hit[0]
    return out


async def get_live_price_map(keys: set[PriceKey]) -> dict[PriceKey, float]:
    """Открыть HttpClient и вернуть {(chain,addr_lower): priceUsd}. Никогда не бросает."""
    if not keys:
        return {}
    from ..config import get_settings

    settings = get_settings()
    try:
        async with HttpClient(
            timeout=getattr(settings, "http_timeout_seconds", 10.0), max_retries=2
        ) as http:
            return await fetch_prices_usd(http, settings.dexscreener_base_url, keys)
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_live_price_map failed: %s", exc)
        return {}
