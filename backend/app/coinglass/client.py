"""Async-клиент Coinglass API v4 (деривативы: funding/OI/ликвидации/long-short).

Контракт v4 — ПОДТВЕРЖДЁН живьём с VPS на тарифе HOBBYIST ($35) на 2026-11-23:
  Base URL:  https://open-api-v4.coinglass.com  (настраивается coinglass_base_url)
  Auth:      заголовок  CG-API-KEY: <key>        (ключ ТОЛЬКО из settings/env)
  Ответ:     {"code": "0", "data": ...}          (code "0" = успех)

Подтверждённые 200 OK:
  • GET /api/futures/supported-coins          → data: список символов (BTC,ETH,SOL,...)
  • GET /api/futures/funding-rate/exchange-list?symbol=BTC
        → data[].stablecoin_margin_list[] = {exchange, funding_rate, ...}

Гейтинг тарифа: мелкие интервалы (1h и ниже) отдают 403 «not available for your
current API plan». HOBBYIST поддерживает {4h,6h,8h,12h,1d} → дефолт 4h. Любой
403/не-200/плановый гейт обрабатывается GRACEFUL → метод возвращает None, не падает.

Пути эндпоинтов — module-level константы: если Coinglass переименует путь или
другой тариф откроет иные эндпоинты, правка в одном месте без изменения логики.

Короткий in-memory TTL-кэш (coinglass_cache_seconds) бережёт лимит платного
тарифа: повторный одинаковый запрос в пределах TTL берётся из памяти.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from ..config import Settings
from ..discovery.base import HttpClient

logger = logging.getLogger("altsr.coinglass")

# --- Пути эндпоинтов v4. Подтверждённые — помечены; остальные защитны к 403. ---
# Подтверждён живьём (200): список поддерживаемых символов.
SUPPORTED_COINS_PATH = "/api/futures/supported-coins"
# Подтверждён живьём (200): funding по биржам (снимок), data[].stablecoin_margin_list[].
FUNDING_RATE_PATH = "/api/futures/funding-rate/exchange-list"
# Подтверждён путь (liquidation/history); на HOBBYIST нужен interval из {4h..1d}.
LIQUIDATION_PATH = "/api/futures/liquidation/history"
# Защитно (может быть гейтнут тарифом → 403 → None): агрегированный OI (OHLC).
OPEN_INTEREST_PATH = "/api/futures/open-interest/ohlc-aggregated-history"
# Защитно (может быть гейтнут тарифом → 403 → None): глобальный L/S account ratio.
LONG_SHORT_PATH = "/api/futures/global-long-short-account-ratio/history"

AUTH_HEADER = "CG-API-KEY"


class CoinglassClient:
    """Тонкий клиент поверх проектного HttpClient. Все методы graceful → None при сбое.

    Использование::

        async with CoinglassClient(settings) as cg:
            funding = await cg.funding_rate("BTC")
    """

    def __init__(
        self,
        settings: Settings,
        *,
        http: HttpClient | None = None,
    ) -> None:
        self._settings = settings
        self._http = http
        self._owns_http = http is None
        # Кэш: path+params → (expires_epoch, payload).
        self._cache: dict[str, tuple[float, Any]] = {}

    async def __aenter__(self) -> "CoinglassClient":
        if self._http is None:
            self._http = HttpClient(timeout=self._settings.http_timeout_seconds)
            await self._http.__aenter__()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._owns_http and self._http is not None:
            await self._http.__aexit__(*exc)

    # --- Внутреннее: один защищённый GET с кэшем. ---
    def _cache_key(self, path: str, params: dict[str, Any]) -> str:
        items = ",".join(f"{k}={v}" for k, v in sorted(params.items()))
        return f"{path}?{items}"

    async def _get(self, path: str, params: dict[str, Any]) -> Any | None:
        """GET к Coinglass. Возвращает поле data (list|dict) или None (graceful).

        403 (гейтинг тарифа), не-200, code!="0", отсутствие data → None + warning.
        """
        settings = self._settings
        if not settings.coinglass_api_key:
            logger.warning("Coinglass: COINGLASS_API_KEY не задан — пропускаю %s", path)
            return None
        if self._http is None:
            logger.warning("Coinglass: клиент используется вне контекста (нет HttpClient)")
            return None

        key = self._cache_key(path, params)
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached is not None and cached[0] > now:
            return cached[1]

        url = f"{settings.coinglass_base_url.rstrip('/')}{path}"
        headers = {AUTH_HEADER: settings.coinglass_api_key, "accept": "application/json"}
        status, payload = await self._http.get_json_status(url, headers=headers, params=params)

        if status == 403:
            # Эндпоинт/интервал не входит в тариф — ожидаемо, не ошибка данных.
            logger.warning("Coinglass %s: 403 — недоступно на текущем тарифе", path)
            return None
        if status != 200 or not isinstance(payload, dict):
            logger.warning("Coinglass %s: не-200 или пустой ответ (status=%s)", path, status)
            return None
        # v4: code=="0" → успех; иначе сообщение об ошибке (лимит/ключ/путь/тариф).
        code = str(payload.get("code", ""))
        if code not in ("0", "", "success"):
            logger.warning(
                "Coinglass %s: code=%s msg=%s", path, code, str(payload.get("msg"))[:120]
            )
            return None
        data = payload.get("data")
        if data is None:
            logger.warning("Coinglass %s: нет поля data", path)
            return None

        ttl = max(1, settings.coinglass_cache_seconds)
        self._cache[key] = (now + ttl, data)
        return data

    def _interval(self, override: str | None) -> str:
        return override or self._settings.coinglass_interval

    # --- Публичные методы по выбранным эндпоинтам. ---
    async def supported_coins(self) -> list[str] | None:
        """Список поддерживаемых символов (подтверждён живьём). None при сбое."""
        data = await self._get(SUPPORTED_COINS_PATH, {})
        if isinstance(data, list):
            return [str(x) for x in data]
        return None

    async def funding_rate(self, symbol: str = "BTC") -> list[dict] | None:
        """Funding по биржам (снимок): data[] с stablecoin_margin_list[]. Подтверждён."""
        data = await self._get(FUNDING_RATE_PATH, {"symbol": symbol})
        return data if isinstance(data, list) else None

    async def open_interest(
        self, symbol: str = "BTC", *, interval: str | None = None, limit: int = 30
    ) -> list[dict] | None:
        """Агрегированный OI (OHLC-история). Может быть гейтнут тарифом → None."""
        data = await self._get(
            OPEN_INTEREST_PATH,
            {"symbol": symbol, "interval": self._interval(interval), "limit": limit},
        )
        return data if isinstance(data, list) else None

    async def liquidations(
        self, symbol: str = "BTC", *, interval: str | None = None, limit: int = 14
    ) -> list[dict] | None:
        """Ликвидации (long/short в USD) по интервалам. HOBBYIST: interval из {4h..1d}."""
        data = await self._get(
            LIQUIDATION_PATH,
            {"symbol": symbol, "interval": self._interval(interval), "limit": limit},
        )
        return data if isinstance(data, list) else None

    async def long_short_ratio(
        self, symbol: str = "BTC", *, interval: str | None = None, limit: int = 14
    ) -> list[dict] | None:
        """Глобальное long/short account ratio. Может быть гейтнут тарифом → None."""
        data = await self._get(
            LONG_SHORT_PATH,
            {"symbol": symbol, "interval": self._interval(interval), "limit": limit},
        )
        return data if isinstance(data, list) else None
