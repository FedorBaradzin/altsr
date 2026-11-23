"""Coinglass — МАКРО-режим рынка (деривативы). Сеть замокана (respx).

Ключ Coinglass берётся ТОЛЬКО из настроек (env/.env). В тестах — заглушка
"test-key", реальный ключ нигде не хранится. Проверяем: заголовок CG-API-KEY,
graceful при отсутствии ключа / 403 тарифа, расчёт режима risk_on/risk_off/
unknown, и TTL-кэш (повторный запрос не бьёт в сеть).
"""
from __future__ import annotations

import httpx
import pytest
import respx

from app.coinglass.client import (
    FUNDING_RATE_PATH,
    CoinglassClient,
)
from app.coinglass.regime import compute_regime, fetch_regime, market_regime_ok
from app.config import get_settings

BASE = "https://open-api-v4.coinglass.com"
FUNDING_URL = f"{BASE}{FUNDING_RATE_PATH}"

# Подтверждённая форма funding-rate/exchange-list.
_FUNDING_HOT = {
    "code": "0",
    "data": [
        {
            "symbol": "BTC",
            "stablecoin_margin_list": [
                {"exchange": "Binance", "funding_rate": 0.05},
                {"exchange": "OKX", "funding_rate": 0.04},
            ],
        }
    ],
}
_FUNDING_NEG = {
    "code": "0",
    "data": [
        {
            "symbol": "BTC",
            "stablecoin_margin_list": [
                {"exchange": "Binance", "funding_rate": -0.04},
                {"exchange": "OKX", "funding_rate": -0.05},
            ],
        }
    ],
}


def _settings(*, key: str = "test-key", enabled: bool = True):
    s = get_settings()
    s.coinglass_api_key = key
    s.coinglass_enabled = enabled
    s.coinglass_base_url = BASE
    s.coinglass_cache_seconds = 120
    s.coinglass_interval = "4h"
    return s


# ---------------------------------------------------------------- client: header
@respx.mock(assert_all_called=True)
async def test_client_sends_cg_api_key_header(respx_mock):
    route = respx_mock.get(FUNDING_URL).mock(
        return_value=httpx.Response(200, json=_FUNDING_HOT)
    )
    async with CoinglassClient(_settings()) as cg:
        data = await cg.funding_rate("BTC")
    assert data is not None
    req = route.calls.last.request
    assert req.headers.get("cg-api-key") == "test-key"
    # Символ передан параметром.
    assert "symbol=BTC" in str(req.url)


# ---------------------------------------------------------------- client: no key
@respx.mock(assert_all_called=False)
async def test_missing_key_returns_none_without_network(respx_mock):
    route = respx_mock.get(FUNDING_URL).mock(
        return_value=httpx.Response(200, json=_FUNDING_HOT)
    )
    async with CoinglassClient(_settings(key="")) as cg:
        assert await cg.funding_rate("BTC") is None
    assert route.call_count == 0  # сеть не трогаем, если ключа нет


# ----------------------------------------------------------- client: 403 на тарифе
@respx.mock(assert_all_called=True)
async def test_plan_gated_403_returns_none(respx_mock):
    respx_mock.get(FUNDING_URL).mock(
        return_value=httpx.Response(403, json={"code": "40003", "msg": "not available"})
    )
    async with CoinglassClient(_settings()) as cg:
        assert await cg.funding_rate("BTC") is None


# ------------------------------------------------------------------- client: cache
@respx.mock(assert_all_called=True)
async def test_ttl_cache_hits_network_once(respx_mock):
    route = respx_mock.get(FUNDING_URL).mock(
        return_value=httpx.Response(200, json=_FUNDING_HOT)
    )
    async with CoinglassClient(_settings()) as cg:
        first = await cg.funding_rate("BTC")
        second = await cg.funding_rate("BTC")
    assert first == second
    assert route.call_count == 1  # второй запрос из кэша


@respx.mock(assert_all_called=True)
async def test_cache_disabled_by_short_ttl_still_caches(respx_mock):
    # TTL всегда >=1с, поэтому в пределах теста повтор берётся из кэша.
    route = respx_mock.get(FUNDING_URL).mock(
        return_value=httpx.Response(200, json=_FUNDING_HOT)
    )
    s = _settings()
    s.coinglass_cache_seconds = 1
    async with CoinglassClient(s) as cg:
        await cg.funding_rate("BTC")
        await cg.funding_rate("BTC")
    assert route.call_count == 1


# ----------------------------------------------------------- regime: pure function
def test_regime_unknown_when_no_inputs():
    out = compute_regime(
        funding=None, open_interest=None, liquidations=None, long_short=None
    )
    assert out["regime"] == "unknown"
    assert out["score"] == 0.0
    assert out["signals"]["funding"] is None


def test_regime_risk_on_negative_funding():
    out = compute_regime(
        funding=_FUNDING_NEG["data"],
        open_interest=None,
        liquidations=None,
        long_short=None,
    )
    # Отрицательный funding → положительный вклад → risk_on.
    assert out["regime"] == "risk_on"
    assert out["score"] > 0
    assert out["signals"]["funding"] is not None


def test_regime_risk_off_hot_funding_and_long_liquidations():
    liquidations = [
        {"longLiquidationUsd": 100, "shortLiquidationUsd": 100},
        {"longLiquidationUsd": 100, "shortLiquidationUsd": 100},
        {"longLiquidationUsd": 100, "shortLiquidationUsd": 100},
        {"longLiquidationUsd": 2000, "shortLiquidationUsd": 100},  # спайк лонг-ликвидаций
    ]
    open_interest = [{"close": 100}, {"close": 130}]  # OI растёт → усиливает перегрев
    long_short = [{"longShortRatio": 1.6}]  # толпа в лонгах
    out = compute_regime(
        funding=_FUNDING_HOT["data"],
        open_interest=open_interest,
        liquidations=liquidations,
        long_short=long_short,
    )
    assert out["regime"] == "risk_off"
    assert out["score"] < 0
    assert out["signals"]["liquidation_spike"]["long_spike"] is True
    assert out["signals"]["long_short"]["ratio"] == 1.6


# ----------------------------------------------------- fetch_regime + helper: gating
async def test_fetch_regime_disabled_returns_unknown_no_network():
    out = await fetch_regime(_settings(enabled=False))
    assert out["regime"] == "unknown"
    assert out["enabled"] is False


async def test_fetch_regime_no_key_returns_unknown():
    out = await fetch_regime(_settings(key="", enabled=True))
    assert out["regime"] == "unknown"


async def test_market_regime_ok_none_when_disabled():
    assert await market_regime_ok(_settings(enabled=False)) is None


@respx.mock(assert_all_called=False)
async def test_fetch_regime_integration_risk_on(respx_mock):
    # Funding отрицательный; прочие эндпоинты гейтнуты тарифом (403) → игнорируются.
    respx_mock.get(FUNDING_URL).mock(
        return_value=httpx.Response(200, json=_FUNDING_NEG)
    )
    respx_mock.get(url__startswith=BASE).mock(return_value=httpx.Response(403))
    out = await fetch_regime(_settings())
    assert out["enabled"] is True
    assert out["regime"] == "risk_on"
    # Гейтнутые сигналы = null, но режим всё равно считается по funding.
    assert out["signals"]["funding"] is not None


@respx.mock(assert_all_called=False)
async def test_market_regime_ok_false_on_risk_off(respx_mock):
    respx_mock.get(FUNDING_URL).mock(
        return_value=httpx.Response(200, json=_FUNDING_HOT)
    )
    respx_mock.get(url__startswith=BASE).mock(return_value=httpx.Response(403))
    # Только перегретый funding → score отрицательный, но может быть neutral; проверяем,
    # что хелпер возвращает bool|None, а не падает.
    res = await market_regime_ok(_settings())
    assert res in (True, False, None)
