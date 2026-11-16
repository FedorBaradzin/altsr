"""On-demand скам-чек произвольного контракта: paste address → живой вердикт.

Переиспользует safety.screen_token (GoPlus / honeypot.is / RugCheck / GeckoTerminal):
пользователь вставляет адрес любого токена (а не только уже найденного ALTSR),
и получает тот же честный вердикт PASS / REVIEW / BLOCK + red_flags, что и лента.

Эндпоинт публичный, поэтому встроены три защиты:
- валидация адреса под сеть (EVM 0x+40hex, Solana base58 32–44) — мусор не доходит
  до провайдеров;
- лёгкий rate-limit по IP (окно + максимум), чтобы один клиент не долбил free-tier API;
- TTL-кэш результатов, чтобы одинаковые адреса не пересканировались каждую секунду.

ЧЕСТНОСТЬ (транслируется в ответе): детекция ловит ЧАСТЬ схем, не все. PASS ≠ «безопасно»
и тем более ≠ «вырастет». Это не инвест-рекомендация.
"""
from __future__ import annotations

import logging
import re
import time
from collections import deque

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator

from ..config import get_settings
from ..discovery.base import HttpClient
from ..safety.goplus import GOPLUS_CHAIN_ID
from ..safety.screener import screen_token

logger = logging.getLogger("altsr.api.scan")

router = APIRouter(prefix="/api", tags=["scan"])

SUPPORTED_CHAINS = ("solana", *GOPLUS_CHAIN_ID.keys())
_EVM_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
# Solana base58: без 0 O I l; минты 32–44 символа.
_SOL_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")

# TTL-кэш результатов скана: key → (ответ, monotonic_ts).
_CACHE_TTL = 120.0
_CACHE_MAX = 2000
_cache: dict[str, tuple[dict, float]] = {}

# Rate-limit по IP: не более _RL_MAX сканов за _RL_WINDOW секунд.
_RL_WINDOW = 60.0
_RL_MAX = 12
_RL_MAX_IPS = 5000
_hits: dict[str, deque[float]] = {}

_DISCLAIMER = (
    "Проверка ловит ЧАСТЬ схем, не все (slow-rug и новые паттерны проскакивают). "
    "PASS ≠ «безопасно» и ≠ «вырастет». Это не инвест-рекомендация."
)


def _valid_address(chain: str, address: str) -> bool:
    if chain == "solana":
        return bool(_SOL_RE.match(address))
    return bool(_EVM_RE.match(address))


def _rate_limited(ip: str) -> bool:
    """Скользящее окно по IP. Возвращает True, если лимит превышен."""
    now = time.monotonic()
    if len(_hits) > _RL_MAX_IPS:
        _hits.clear()  # грубая защита от роста памяти при массовом скане
    dq = _hits.setdefault(ip, deque())
    while dq and now - dq[0] > _RL_WINDOW:
        dq.popleft()
    if len(dq) >= _RL_MAX:
        return True
    dq.append(now)
    return False


def _cache_get(key: str) -> dict | None:
    hit = _cache.get(key)
    if hit is None:
        return None
    payload, ts = hit
    if time.monotonic() - ts >= _CACHE_TTL:
        _cache.pop(key, None)
        return None
    return payload


def _cache_put(key: str, payload: dict) -> None:
    if len(_cache) >= _CACHE_MAX:
        _cache.clear()
    _cache[key] = (payload, time.monotonic())


class ScanIn(BaseModel):
    chain: str
    address: str

    @field_validator("chain")
    @classmethod
    def _norm_chain(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in SUPPORTED_CHAINS:
            raise ValueError(
                "Неподдерживаемая сеть. Доступно: " + ", ".join(SUPPORTED_CHAINS)
            )
        return v

    @field_validator("address")
    @classmethod
    def _norm_address(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Пустой адрес")
        return v


def _result_to_dict(result, *, cached: bool) -> dict:
    # Какие ключевые сигналы реально удалось проверить (честность: что осмотрели).
    f = result.findings
    checked = {
        "honeypot": f.is_honeypot is not None,
        "sell_tax": f.sell_tax is not None,
        "mint_authority": f.mint_authority_active is not None,
        "holders": f.top_holder_pct is not None or f.holder_count is not None,
        "lp_lock": f.lp_locked is not None,
    }
    return {
        "chain": result.chain,
        "address": result.address,
        "verdict": result.verdict,
        "risk_score": result.risk_score,
        "is_malicious": result.is_malicious,
        "red_flags": result.red_flags_as_dicts(),
        "sources": list(f.sources),
        "checked": checked,
        "disclaimer": _DISCLAIMER,
        "cached": cached,
    }


@router.post("/scan")
async def scan(payload: ScanIn, request: Request) -> dict:
    """Проверить произвольный контракт на скам прямо сейчас."""
    chain, address = payload.chain, payload.address
    if not _valid_address(chain, address):
        raise HTTPException(
            status_code=422, detail="Некорректный адрес контракта для этой сети"
        )

    ip = request.client.host if request.client else "unknown"
    if _rate_limited(ip):
        raise HTTPException(
            status_code=429,
            detail="Слишком много проверок. Подождите минуту и попробуйте снова.",
        )

    key = f"{chain}:{address.lower()}"
    cached = _cache_get(key)
    if cached is not None:
        return {**cached, "cached": True}

    settings = get_settings()
    try:
        async with HttpClient(
            timeout=settings.http_timeout_seconds, max_retries=1
        ) as http:
            result = await screen_token(http, settings, chain, address)
    except Exception as exc:  # noqa: BLE001 — внешние провайдеры ненадёжны
        logger.warning("scan: не удалось проверить %s:%s — %s", chain, address, exc)
        raise HTTPException(
            status_code=502,
            detail="Не удалось получить данные от провайдеров безопасности. "
            "Попробуйте ещё раз через минуту.",
        ) from exc

    out = _result_to_dict(result, cached=False)
    _cache_put(key, out)
    return out
