"""GeckoTerminal new_pools — новые пулы по сетям (EVM + Solana), без ключа.

Эндпоинт: GET {base}/networks/{network}/new_pools
Docs-форма ответа — JSON:API (data[] + included[]).

T10 (кросс-проверка источников): плюс независимое подтверждение тренда по OHLCV
того же пула. HTTP-часть (fetch_ohlcv) отделена от чистой логики тренда
(confirm_trend / trend_score), которая детерминирована и покрыта unit-тестами.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
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


# --------------------------------------------------------------------------- #
# OHLCV: подтверждение тренда (T10)                                            #
# --------------------------------------------------------------------------- #

# Доступные таймфреймы GeckoTerminal OHLCV.
OHLCV_TIMEFRAMES = ("day", "hour", "minute")


@dataclass(slots=True)
class Candle:
    """Одна свеча OHLCV. Время — unix-секунды (aware UTC не нужен для тренда)."""

    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float


def parse_ohlcv(payload: Any) -> list[Candle]:
    """Разобрать ответ GeckoTerminal OHLCV в список свечей, упорядоченный по времени.

    Форма: data.attributes.ohlcv_list = [[ts, open, high, low, close, volume], ...].
    GeckoTerminal отдаёт свечи «новые сначала» — сортируем по ts по возрастанию,
    чтобы логика тренда была детерминированной.
    """
    if not isinstance(payload, dict):
        return []
    attrs = ((payload.get("data") or {}).get("attributes") or {})
    rows = attrs.get("ohlcv_list") or []
    candles: list[Candle] = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            continue
        ts = parse_ts(row[0])
        o, h, lo, c, v = (to_float(row[1]), to_float(row[2]),
                          to_float(row[3]), to_float(row[4]), to_float(row[5]))
        if None in (o, h, lo, c, v) or ts is None:
            continue
        candles.append(Candle(int(ts.timestamp()), o, h, lo, c, v))
    candles.sort(key=lambda x: x.ts)
    return candles


def trend_score(candles: Sequence[Candle]) -> float:
    """Доля растущих баров (close[i] > close[i-1]) в ряду, 0..1.

    Чистая метрика силы восходящего тренда. Пустой/короткий ряд → 0.0.
    """
    closes = [c.close for c in candles]
    if len(closes) < 2:
        return 0.0
    ups = sum(1 for a, b in zip(closes, closes[1:], strict=False) if b > a)
    return ups / (len(closes) - 1)


def confirm_trend(
    candles: Sequence[Candle],
    *,
    min_candles: int = 5,
    min_up_fraction: float = 0.5,
    min_net_change: float = 0.0,
) -> bool:
    """Подтверждён ли восходящий тренд пула по OHLCV.

    Консервативно: нужно ≥ min_candles свечей, итоговый рост цены больше
    min_net_change (доля, напр. 0.0 = просто выше старта) И доля растущих
    баров ≥ min_up_fraction. «Нет данных» → False (не подтверждаем вслепую).
    """
    if len(candles) < min_candles:
        return False
    first_close = candles[0].close
    last_close = candles[-1].close
    if first_close <= 0:
        return False
    net_change = (last_close - first_close) / first_close
    if net_change <= min_net_change:
        return False
    return trend_score(candles) >= min_up_fraction


async def fetch_ohlcv(
    http: HttpClient,
    base_url: str,
    network: str,
    pool_address: str,
    *,
    timeframe: str = "hour",
    aggregate: int = 1,
    limit: int = 100,
    currency: str = "usd",
) -> list[Candle]:
    """Забрать последние OHLCV-свечи пула. Сеть — имя GeckoTerminal (eth/base/solana).

    GET {base}/networks/{network}/pools/{pool}/ohlcv/{timeframe}. На ошибке → [].
    """
    if timeframe not in OHLCV_TIMEFRAMES:
        raise ValueError(f"timeframe должен быть из {OHLCV_TIMEFRAMES}, получено {timeframe!r}")
    url = f"{base_url}/networks/{network}/pools/{pool_address}/ohlcv/{timeframe}"
    payload = await http.get_json(
        url, params={"aggregate": aggregate, "limit": limit, "currency": currency}
    )
    return parse_ohlcv(payload)


async def confirm_pool_trend(
    http: HttpClient,
    base_url: str,
    network: str,
    pool_address: str,
    *,
    timeframe: str = "hour",
    min_candles: int = 5,
    min_up_fraction: float = 0.5,
) -> bool:
    """Удобный хелпер: забрать OHLCV и вернуть булево подтверждение тренда.

    Падение HTTP → пустой ряд → False (кросс-проверка не подтверждает).
    """
    candles = await fetch_ohlcv(http, base_url, network, pool_address, timeframe=timeframe)
    return confirm_trend(candles, min_candles=min_candles, min_up_fraction=min_up_fraction)
