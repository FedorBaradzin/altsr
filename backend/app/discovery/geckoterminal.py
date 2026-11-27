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

# Обратное отображение: наш канонический chain → имя сети в GeckoTerminal.
# Нужно для OHLCV/графиков, где путь строится по сети Gecko (eth/base/bsc/...).
CHAIN_TO_NETWORK = {
    "ethereum": "eth",
    "eth": "eth",
    "base": "base",
    "bsc": "bsc",
    "polygon": "polygon_pos",
    "polygon_pos": "polygon_pos",
    "arbitrum": "arbitrum",
    "solana": "solana",
}


def chain_to_network(chain: str | None) -> str | None:
    """Канонический chain → имя сети GeckoTerminal, либо None если не поддержано."""
    return CHAIN_TO_NETWORK.get((chain or "").strip().lower())


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

    # Логотип токена: image_url из атрибутов base_token (включён через include=base_token).
    # CoinGecko отдаёт "missing.png"/пусто когда картинки нет — такое отбрасываем.
    image_url = base_attrs.get("image_url")
    if not image_url or "missing" in str(image_url).lower():
        image_url = None

    chain = NETWORK_TO_CHAIN.get(network, network)
    # Изменение цены по окнам (%) — из price_change_percentage (строки). Всё из того
    # же keyless-ответа, без доп. запросов и без платного ключа.
    pcp = attrs.get("price_change_percentage") or {}

    def _pc(k: str) -> float | None:
        return to_float(pcp.get(k)) if isinstance(pcp, dict) else None

    vol = attrs.get("volume_usd") or {}
    volume_h24 = to_float(vol.get("h24")) if isinstance(vol, dict) else None

    txns = attrs.get("transactions") or {}
    th24 = txns.get("h24") if isinstance(txns, dict) else None
    txns_h24: int | None = None
    if isinstance(th24, dict):
        try:
            txns_h24 = int(th24.get("buys") or 0) + int(th24.get("sells") or 0)
        except (TypeError, ValueError):
            txns_h24 = None

    return NormalizedToken(
        chain=chain,
        address=address,
        source="geckoterminal",
        symbol=base_attrs.get("symbol") or (attrs.get("name") or "").split(" / ")[0] or None,
        name=base_attrs.get("name") or attrs.get("name"),
        image_url=image_url,
        created_at=parse_ts(attrs.get("pool_created_at")),
        liquidity_usd=to_float(attrs.get("reserve_in_usd")),
        fdv=to_float(attrs.get("fdv_usd")),
        price_usd=to_float(attrs.get("base_token_price_usd")),
        price_change_h24=_pc("h24"),
        price_change_h1=_pc("h1"),
        price_change_h6=_pc("h6"),
        volume_h24=volume_h24,
        txns_h24=txns_h24,
        market_cap_usd=to_float(attrs.get("market_cap_usd")),
        pair_address=attrs.get("address"),
        dex=dex_ref,
        socials=socials,
    )


async def fetch_new_pools(
    http: HttpClient, base_url: str, networks: list[str],
    *, headers: dict[str, str] | None = None,
) -> list[NormalizedToken]:
    results: list[NormalizedToken] = []
    for network in networks:
        url = f"{base_url}/networks/{network}/new_pools"
        payload = await http.get_json(url, params={"include": "base_token,dex"}, headers=headers)
        if not isinstance(payload, dict):
            continue
        included = _index_included(payload)
        for pool in payload.get("data", []) or []:
            tok = normalize_pool(pool, included, network)
            if tok and tok.is_valid:
                results.append(tok)
    logger.info("GeckoTerminal: %d токенов из %d сетей", len(results), len(networks))
    return results


async def fetch_trending_pools(
    http: HttpClient, base_url: str, networks: list[str],
    *, headers: dict[str, str] | None = None,
) -> list[NormalizedToken]:
    """Trending-пулы (активно торгуемые качественные токены) по сетям.

    Зеркалит fetch_new_pools, но бьёт в GET {base}/networks/{network}/trending_pools.
    Тот же JSON:API-парсинг (_index_included + normalize_pool). Токены помечаются
    source="geckoterminal_trending", чтобы downstream мог отличить их от new_pools.
    """
    results: list[NormalizedToken] = []
    for network in networks:
        url = f"{base_url}/networks/{network}/trending_pools"
        payload = await http.get_json(url, params={"include": "base_token,dex"}, headers=headers)
        if not isinstance(payload, dict):
            continue
        included = _index_included(payload)
        for pool in payload.get("data", []) or []:
            tok = normalize_pool(pool, included, network)
            if tok and tok.is_valid:
                tok.source = "geckoterminal_trending"
                results.append(tok)
    logger.info("GeckoTerminal trending: %d токенов из %d сетей", len(results), len(networks))
    return results


async def fetch_top_pools(
    http: HttpClient, base_url: str, networks: list[str], *, pages: int = 1,
    headers: dict[str, str] | None = None,
) -> list[NormalizedToken]:
    """ТОП-пулы по 24ч-объёму (устоявшиеся ликвидные монеты, что «долго в топе»).

    Бьёт в GET {base}/networks/{network}/pools?sort=h24_volume_usd_desc. Это НАСТОЯЩИЙ
    топ-универсум (а не трендовый ручеёк): высокообъёмные пулы с реальной ликвидностью.
    Тот же JSON:API-парсинг. Токены помечаются source="geckoterminal_top", чтобы
    downstream мог предпочесть их при отборе кандидатов и пройти soft-гейт качества.
    pages>1 — берём несколько страниц (по ~20 пулов) для более широкого топ-пула.
    """
    results: list[NormalizedToken] = []
    for network in networks:
        for page in range(1, max(1, pages) + 1):
            url = f"{base_url}/networks/{network}/pools"
            payload = await http.get_json(
                url,
                params={
                    "include": "base_token,dex",
                    "sort": "h24_volume_usd_desc",
                    "page": page,
                },
                headers=headers,
            )
            if not isinstance(payload, dict):
                break
            data = payload.get("data", []) or []
            if not data:
                break
            included = _index_included(payload)
            for pool in data:
                tok = normalize_pool(pool, included, network)
                if tok and tok.is_valid:
                    tok.source = "geckoterminal_top"
                    results.append(tok)
    logger.info("GeckoTerminal top: %d токенов из %d сетей", len(results), len(networks))
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
    headers: dict[str, str] | None = None,
) -> list[Candle]:
    """Забрать последние OHLCV-свечи пула. Сеть — имя GeckoTerminal (eth/base/solana).

    GET {base}/networks/{network}/pools/{pool}/ohlcv/{timeframe}. На ошибке → [].
    """
    if timeframe not in OHLCV_TIMEFRAMES:
        raise ValueError(f"timeframe должен быть из {OHLCV_TIMEFRAMES}, получено {timeframe!r}")
    url = f"{base_url}/networks/{network}/pools/{pool_address}/ohlcv/{timeframe}"
    payload = await http.get_json(
        url, params={"aggregate": aggregate, "limit": limit, "currency": currency},
        headers=headers,
    )
    return parse_ohlcv(payload)


async def fetch_categories(
    http: HttpClient, base_url: str, *, limit: int = 20,
    headers: dict[str, str] | None = None,
) -> list[dict]:
    """GeckoTerminal он-чейн категории (нарративы: AI, memes, …) — item 5.

    GET {base}/categories (JSON:API). Отдаёт список {id, name, market_cap_usd,
    volume_24h_usd, top pools...}. Keyless-поддержка не гарантирована: при любом
    сбое/гейтинге → [] (graceful, вызывающий сам решает показывать ли блок).
    """
    url = f"{base_url}/categories"
    payload = await http.get_json(url, params={"page": 1}, headers=headers)
    if not isinstance(payload, dict):
        return []
    out: list[dict] = []
    for item in payload.get("data", []) or []:
        attrs = item.get("attributes", {}) or {}
        name = attrs.get("name")
        if not name:
            continue
        out.append(
            {
                "id": item.get("id"),
                "name": name,
                "market_cap_usd": to_float(attrs.get("market_cap_usd")),
                "volume_24h_usd": to_float(
                    attrs.get("h24_volume_usd") or attrs.get("volume_usd")
                ),
                "change_24h": to_float(
                    (attrs.get("market_cap_change_percentage") or {}).get("h24")
                    if isinstance(attrs.get("market_cap_change_percentage"), dict)
                    else attrs.get("fdv_change_percentage_h24")
                ),
            }
        )
        if len(out) >= limit:
            break
    return out


async def confirm_pool_trend(
    http: HttpClient,
    base_url: str,
    network: str,
    pool_address: str,
    *,
    timeframe: str = "hour",
    min_candles: int = 5,
    min_up_fraction: float = 0.5,
    headers: dict[str, str] | None = None,
) -> bool:
    """Удобный хелпер: забрать OHLCV и вернуть булево подтверждение тренда.

    Падение HTTP → пустой ряд → False (кросс-проверка не подтверждает).
    """
    candles = await fetch_ohlcv(
        http, base_url, network, pool_address, timeframe=timeframe, headers=headers
    )
    return confirm_trend(candles, min_candles=min_candles, min_up_fraction=min_up_fraction)


# --------------------------------------------------------------------------- #
# Сделки и холдеры (нужен платный ключ для масштаба) — для «раннего входа»      #
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class TradesAgg:
    """Агрегат ленты сделок пула: перевес покупок/продаж."""

    buys: int = 0
    sells: int = 0
    buyers: int = 0
    sellers: int = 0
    buy_vol_usd: float = 0.0
    sell_vol_usd: float = 0.0

    @property
    def total(self) -> int:
        return self.buys + self.sells

    @property
    def buy_pressure(self) -> float | None:
        """(buys−sells)/(buys+sells) ∈ [−1,1]. None при < 5 сделок (мало данных)."""
        t = self.buys + self.sells
        return (self.buys - self.sells) / t if t >= 5 else None

    @property
    def vol_buy_pressure(self) -> float | None:
        """Перевес по объёму покупок над продажами ∈ [−1,1]."""
        t = self.buy_vol_usd + self.sell_vol_usd
        return (self.buy_vol_usd - self.sell_vol_usd) / t if t > 0 else None


async def fetch_token_top_pool(
    http: HttpClient,
    base_url: str,
    network: str,
    token_address: str,
    *,
    headers: dict[str, str] | None = None,
) -> str | None:
    """Адрес самого ликвидного пула токена. Нужен, когда у нас есть только адрес
    минта (напр. Solana pump.fun), а для сделок/OHLCV требуется адрес ПУЛА.
    GET {base}/networks/{net}/tokens/{addr}/pools → первый (по ликвидности). None на ошибке."""
    url = f"{base_url}/networks/{network}/tokens/{token_address}/pools"
    try:
        payload = await http.get_json(url, headers=headers)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(payload, dict):
        return None
    pools = payload.get("data") or []
    if not pools:
        return None
    attrs = pools[0].get("attributes", {}) or {}
    return attrs.get("address")


async def fetch_pool_trades(
    http: HttpClient,
    base_url: str,
    network: str,
    pool_address: str,
    *,
    window_minutes: int = 0,
    headers: dict[str, str] | None = None,
) -> TradesAgg:
    """Агрегат последних сделок пула (до ~300 за 24ч).

    GET {base}/networks/{net}/pools/{addr}/trades. window_minutes>0 — считать только
    сделки за последние N минут. На ошибке → пустой TradesAgg (graceful)."""
    from datetime import datetime, timedelta, timezone

    agg = TradesAgg()
    url = f"{base_url}/networks/{network}/pools/{pool_address}/trades"
    payload = await http.get_json(url, headers=headers)
    if not isinstance(payload, dict):
        return agg
    cutoff = None
    if window_minutes > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    buyers: set[str] = set()
    sellers: set[str] = set()
    for tr in payload.get("data", []) or []:
        a = tr.get("attributes", {}) or {}
        if cutoff is not None:
            ts = parse_ts(a.get("block_timestamp"))
            if ts is not None and ts < cutoff:
                continue
        kind = (a.get("kind") or "").lower()
        wallet = a.get("tx_from_address") or ""
        vol = to_float(a.get("volume_in_usd")) or 0.0
        if kind == "buy":
            agg.buys += 1
            agg.buy_vol_usd += vol
            if wallet:
                buyers.add(wallet)
        elif kind == "sell":
            agg.sells += 1
            agg.sell_vol_usd += vol
            if wallet:
                sellers.add(wallet)
    agg.buyers = len(buyers)
    agg.sellers = len(sellers)
    return agg


async def fetch_top_holders(
    http: HttpClient,
    base_url: str,
    network: str,
    token_address: str,
    *,
    headers: dict[str, str] | None = None,
) -> dict | None:
    """Распределение холдеров токена (платный onchain-эндпоинт).

    GET {base}/networks/{net}/tokens/{addr}/top_holders. Возвращает
    {count, top10_pct} или None (graceful: эндпоинт может быть недоступен на плане
    или формат иной). top10_pct — концентрация у топ-10 (риск рага, чем выше тем хуже)."""
    url = f"{base_url}/networks/{network}/tokens/{token_address}/top_holders"
    payload = await http.get_json(url, headers=headers)
    if not isinstance(payload, dict):
        return None
    attrs = ((payload.get("data") or {}).get("attributes") or {})
    holders = attrs.get("holders")
    count = attrs.get("count")
    if count is None:
        count = attrs.get("total_holders")
    if isinstance(holders, list) and holders:
        top10 = 0.0
        for h in holders[:10]:
            p = to_float((h or {}).get("percentage"))
            if p is not None:
                top10 += p
        n = int(count) if isinstance(count, (int, float)) else len(holders)
        return {"count": n, "top10_pct": round(top10, 2) if top10 else None}
    if isinstance(count, (int, float)):
        return {"count": int(count), "top10_pct": None}
    return None
