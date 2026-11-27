"""GeckoTerminal pool-trades — последние сделки пула (без ключа).

Эндпоинт: GET {base}/networks/{network}/pools/{pool_address}/trades
Форма ответа — JSON:API (data[] c attributes). Без ключа GeckoTerminal отдаёт
последние ~300 сделок за ~24ч (newest-first); пагинация/trading_period требуют
платного плана, поэтому полагаемся только на это окно (см. ограничения в
service.py).

ВАЖНО: эта HTTP-часть живёт в модуле smartmoney и НЕ трогает discovery/
geckoterminal.py (чтобы не конфликтовать с discovery-источником). Парсер
защитный: каждый .get обёрнут, битые записи пропускаются.

Форма attributes одной сделки (проверено по докам CoinGecko onchain):
  block_number (int), tx_hash (str), tx_from_address (str),
  from_token_amount/to_token_amount (str), price_*_in_usd (str),
  block_timestamp (ISO-строка), kind ("buy"|"sell"), volume_in_usd (str),
  from_token_address/to_token_address (str), is_anomalous (bool).
tx_from_address — кошелёк инициатора сделки; kind — покупка/продажа базового
токена пула (по умолчанию token=base).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from ..discovery.base import HttpClient, parse_ts, to_float

logger = logging.getLogger("altsr.smartmoney.trades")


@dataclass(slots=True)
class Trade:
    """Одна ончейн-сделка пула (нормализованная, только нужные поля)."""

    wallet: str
    kind: str                 # "buy" | "sell" (относительно базового токена)
    ts: datetime | None       # block_timestamp (aware UTC)
    volume_usd: float | None
    anomalous: bool = False

    @property
    def is_buy(self) -> bool:
        return self.kind == "buy"


def parse_trades(payload: object) -> list[Trade]:
    """Разобрать ответ trades-эндпоинта в список Trade. Защитно: битое → пропуск.

    Нет/некорректные данные → пустой список (НЕ выдумываем сделки).
    """
    if not isinstance(payload, dict):
        return []
    rows = payload.get("data")
    if not isinstance(rows, list):
        return []
    trades: list[Trade] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        attrs = row.get("attributes")
        if not isinstance(attrs, dict):
            continue
        wallet = attrs.get("tx_from_address")
        if not isinstance(wallet, str) or not wallet.strip():
            continue
        kind = attrs.get("kind")
        if kind not in ("buy", "sell"):
            continue
        trades.append(
            Trade(
                wallet=wallet.strip(),
                kind=kind,
                ts=parse_ts(attrs.get("block_timestamp")),
                volume_usd=to_float(attrs.get("volume_in_usd")),
                anomalous=bool(attrs.get("is_anomalous", False)),
            )
        )
    return trades


async def fetch_trades(
    http: HttpClient,
    base_url: str,
    network: str,
    pool_address: str,
    *,
    min_volume_usd: float = 0.0,
) -> list[Trade]:
    """Забрать последние сделки пула. Сеть — имя GeckoTerminal (eth/base/solana).

    На ошибке/пустом ответе → []. Исключает аномальные сделки (is_anomalous).
    """
    url = f"{base_url}/networks/{network}/pools/{pool_address}/trades"
    params: dict[str, object] = {}
    if min_volume_usd > 0:
        params["trade_volume_in_usd_greater_than"] = min_volume_usd
    payload = await http.get_json(url, params=params or None)
    trades = [t for t in parse_trades(payload) if not t.anomalous]
    return trades
