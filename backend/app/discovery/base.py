"""Единая нормализованная модель токена + базовый async HTTP-клиент.

NormalizedToken — то, во что каждый источник обязан привести свой ответ
(п.4 промта). Ключ дедупа — (chain, address), оба в нижнем регистре.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger("altsr.discovery")


@dataclass(slots=True)
class NormalizedToken:
    chain: str
    address: str
    source: str
    symbol: str | None = None
    name: str | None = None
    created_at: datetime | None = None
    liquidity_usd: float | None = None
    fdv: float | None = None
    pair_address: str | None = None
    dex: str | None = None
    socials: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Нормализуем ключ дедупа.
        self.chain = (self.chain or "").strip().lower()
        self.address = (self.address or "").strip().lower()

    @property
    def dedup_key(self) -> str:
        return f"{self.chain}:{self.address}"

    @property
    def is_valid(self) -> bool:
        return bool(self.chain and self.address)

    def socials_json(self) -> str | None:
        return json.dumps(self.socials, ensure_ascii=False) if self.socials else None


def parse_ts(value: Any) -> datetime | None:
    """Разобрать время из ISO-строки или unix-секунд/мс в aware UTC."""
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            # Эвристика: миллисекунды, если число слишком большое.
            seconds = value / 1000 if value > 10_000_000_000 else value
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


class HttpClient:
    """Тонкая обёртка над httpx с ретраями и экспоненциальным backoff."""

    def __init__(
        self,
        *,
        timeout: float = 15.0,
        max_retries: int = 3,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._timeout = timeout
        self._max_retries = max_retries
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> HttpClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                headers={"User-Agent": "altsr-discovery/0.0", "Accept": "application/json"},
            )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    async def post(self, url: str, **kwargs: Any) -> httpx.Response | None:
        """POST без ретраев (для уведомлений). Возвращает Response или None."""
        assert self._client is not None, "HttpClient используется вне контекста"
        try:
            return await self._client.post(url, **kwargs)
        except httpx.HTTPError as exc:
            logger.warning("POST %s не удался: %s", url, exc)
            return None

    async def get_text(self, url: str, **kwargs: Any) -> str | None:
        """GET → текст (для RSS/XML). None при ошибке."""
        assert self._client is not None, "HttpClient используется вне контекста"
        try:
            resp = await self._client.get(url, **kwargs)
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPError as exc:
            logger.warning("GET(text) %s не удался: %s", url, exc)
            return None

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        assert self._client is not None, "HttpClient используется вне контекста"
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                resp = await self._client.get(url, **kwargs)
                # 429/5xx — ретраим; остальные ошибки отдаём наверх через raise_for_status.
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError(
                        "retryable", request=resp.request, response=resp
                    )
                resp.raise_for_status()
                return resp.json()
            except (httpx.HTTPError, json.JSONDecodeError) as exc:
                last_exc = exc
                backoff = min(2**attempt, 10) + (0.1 * attempt)
                logger.warning(
                    "GET %s попытка %d/%d не удалась: %s; backoff %.1fs",
                    url, attempt + 1, self._max_retries, exc, backoff,
                )
                if attempt + 1 < self._max_retries:
                    await asyncio.sleep(backoff)
        logger.error("GET %s исчерпал ретраи: %s", url, last_exc)
        return None
