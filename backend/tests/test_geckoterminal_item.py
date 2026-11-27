"""GeckoTerminal item 1/4/5: chain→network, OHLCV parse, categories parse,
trending как мягкий сигнал входа (SIGNAL_SOFT_TRENDING_ENABLED) и бонус к уверенности.

Чистые юниты без сети: HttpClient подменяется фейком, возвращающим фикстуры.
"""
from __future__ import annotations

from app.config import get_settings
from app.discovery import geckoterminal as gt
from app.signals.engine import SignalInput, evaluate_entry


# --------------------------- chain → network ------------------------------- #
def test_chain_to_network_known():
    assert gt.chain_to_network("ethereum") == "eth"
    assert gt.chain_to_network("BSC") == "bsc"
    assert gt.chain_to_network("polygon") == "polygon_pos"
    assert gt.chain_to_network("solana") == "solana"


def test_chain_to_network_unknown():
    assert gt.chain_to_network("dogechain") is None
    assert gt.chain_to_network(None) is None


# ------------------------------- OHLCV parse ------------------------------- #
def test_parse_ohlcv_sorts_and_filters():
    payload = {
        "data": {
            "attributes": {
                "ohlcv_list": [
                    [2000, 2.0, 2.5, 1.9, 2.4, 1000.0],
                    [1000, 1.0, 1.5, 0.9, 1.4, 500.0],
                    [3000, None, 1, 1, 1, 1],  # битая строка — отбрасывается
                ]
            }
        }
    }
    candles = gt.parse_ohlcv(payload)
    assert [c.ts for c in candles] == [1000, 2000]  # отсортировано по ts возр.
    assert candles[0].close == 1.4


def test_parse_ohlcv_empty_on_garbage():
    assert gt.parse_ohlcv(None) == []
    assert gt.parse_ohlcv({"data": {}}) == []


# ----------------------------- categories parse ---------------------------- #
class _FakeHttp:
    def __init__(self, payload):
        self._payload = payload

    async def get_json(self, url, **kwargs):
        return self._payload


async def test_fetch_categories_parses():
    payload = {
        "data": [
            {
                "id": "ai",
                "attributes": {
                    "name": "AI Agents",
                    "market_cap_usd": "123456.7",
                    "h24_volume_usd": "9999.0",
                },
            },
            {"id": "x", "attributes": {}},  # без name — пропуск
        ]
    }
    cats = await gt.fetch_categories(_FakeHttp(payload), "https://base", limit=20)
    assert len(cats) == 1
    assert cats[0]["name"] == "AI Agents"
    assert cats[0]["market_cap_usd"] == 123456.7


async def test_fetch_categories_graceful_on_garbage():
    assert await gt.fetch_categories(_FakeHttp(None), "https://base") == []


# -------------------- trending как мягкий сигнал входа --------------------- #
def _s():
    s = get_settings()
    s.momentum_enabled = False
    s.indicators_enabled = False
    s.vol_spike_enabled = False
    s.signal_require_smart_money = False
    s.signal_soft_smart_enabled = False
    s.signal_soft_trending_enabled = True
    s.signal_soft_min_smart_wallets = 1
    s.signal_soft_strong_m5 = 3.0
    return s


def _inp(**kw) -> SignalInput:
    base = dict(chain="ethereum", address="0xabc", liquidity_usd=50000.0,
                age_minutes=60.0, verdict="PASS", risk_score=10)
    base.update(kw)
    return SignalInput(**base)


def test_trending_gate_rejects_flat_non_trending():
    # Не в trending, нет smart-money, слабый m5 → отказ (мёртвый плоский мусор).
    d = evaluate_entry(_inp(is_trending=False, smart_wallets=0, price_change_m5=0.5), _s())
    assert not d.passed
    assert "trending" in d.rejected


def test_trending_gate_passes_trending():
    d = evaluate_entry(_inp(is_trending=True, smart_wallets=0, price_change_m5=0.5), _s())
    assert d.passed
    assert any("trending" in r for r in d.reasons)


def test_trending_gate_disabled_is_inert():
    s = _s()
    s.signal_soft_trending_enabled = False
    d = evaluate_entry(_inp(is_trending=False, smart_wallets=0, price_change_m5=0.5), s)
    assert d.passed


def test_trending_confidence_bonus():
    s = get_settings()
    s.momentum_enabled = False
    s.indicators_enabled = False
    s.vol_spike_enabled = False
    s.signal_soft_trending_enabled = False
    s.calibration_enabled = False
    s.signal_conf_w_trending = 0.1
    base = dict(chain="ethereum", address="0xabc", liquidity_usd=50000.0,
                age_minutes=60.0, verdict="PASS", risk_score=10)
    with_trend = evaluate_entry(SignalInput(**base, is_trending=True), s)
    without = evaluate_entry(SignalInput(**base, is_trending=False), s)
    assert with_trend.confidence > without.confidence
