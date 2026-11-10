"""Birdeye — ранний discovery новых листингов (new_listing).

Эндпоинт: GET {base}/defi/v2/tokens/new_listing
Заголовки: X-API-KEY (ключ из env/.env), x-chain (solana/ethereum/base/...).

Ключ НИКОГДА не хранится в коде — только в настройках из окружения.

Исчерпание кредитов / недействительный ключ (401/402/403/429) превращается в
BirdeyeError(needs_topup=True): вызывающий слой шлёт системный алерт «пополни счёт»
в Telegram. 5xx — временная ошибка, не повод для алерта (вернём пустой список).
"""
from __future__ import annotations

import logging
from typing import Any

from .base import HttpClient, NormalizedToken, parse_ts, to_float

logger = logging.getLogger("altsr.discovery.birdeye")

NEW_LISTING_PATH = "/defi/v2/tokens/new_listing"

# Имена сетей Birdeye → наши канонические chain-идентификаторы.
CHAIN_ALIASES = {
    "solana": "solana",
    "ethereum": "ethereum",
    "eth": "ethereum",
    "base": "base",
    "bsc": "bsc",
    "polygon": "polygon",
    "arbitrum": "arbitrum",
    "optimism": "optimism",
}


class BirdeyeError(RuntimeError):
    """Ошибка Birdeye. needs_topup=True → нужен системный алерт о пополнении/ключе."""

    def __init__(self, message: str, *, needs_topup: bool = False) -> None:
        super().__init__(message)
        self.needs_topup = needs_topup


def normalize_new_listing(item: dict, chain: str) -> NormalizedToken | None:
    address = item.get("address")
    if not address:
        return None
    socials: dict[str, Any] = {}
    if item.get("logoURI"):
        socials["logo"] = item["logoURI"]
    return NormalizedToken(
        chain=CHAIN_ALIASES.get(chain.lower(), chain.lower()),
        address=address,
        source="birdeye",
        symbol=item.get("symbol"),
        name=item.get("name"),
        created_at=parse_ts(item.get("liquidityAddedAt")),
        liquidity_usd=to_float(item.get("liquidity")),
        socials=socials,
    )


async def fetch_new_listings(
    http: HttpClient,
    *,
    base_url: str,
    api_key: str,
    chains: list[str],
    limit: int = 20,
) -> list[NormalizedToken]:
    """Собрать свежие листинги по сетям. Бросает BirdeyeError при проблемах с ключом/кредитами."""
    if not api_key:
        raise BirdeyeError("BIRDEYE_API_KEY не задан", needs_topup=False)

    url = f"{base_url.rstrip('/')}{NEW_LISTING_PATH}"
    results: list[NormalizedToken] = []
    for chain in chains:
        headers = {"X-API-KEY": api_key, "x-chain": chain, "accept": "application/json"}
        params = {"limit": max(1, min(limit, 20)), "meme_platform_enabled": "false"}
        status, payload = await http.get_json_status(url, headers=headers, params=params)

        if status in (401, 403):
            raise BirdeyeError(
                "Birdeye вернул 401/403 — ключ недействителен или нет доступа к эндпоинту",
                needs_topup=True,
            )
        if status in (402, 429):
            raise BirdeyeError(
                "Birdeye вернул 402/429 — исчерпаны кредиты или превышен лимит запросов",
                needs_topup=True,
            )
        if not payload or not isinstance(payload, dict):
            # None/5xx/мусор — временная ошибка, пропускаем сеть без алерта.
            logger.warning("Birdeye new_listing(%s): пустой ответ (status=%s)", chain, status)
            continue
        if payload.get("success") is False:
            logger.warning("Birdeye new_listing(%s): success=false %s",
                           chain, str(payload.get("message"))[:120])
            continue

        items = ((payload.get("data") or {}).get("items")) or []
        for item in items:
            tok = normalize_new_listing(item, chain)
            if tok and tok.is_valid:
                results.append(tok)

    logger.info("Birdeye: %d токенов из %d сетей", len(results), len(chains))
    return results
