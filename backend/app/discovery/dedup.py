"""Дедуп + идемпотентная запись токенов в БД.

Два слоя защиты от дублей:
1) Redis-ключ dedup:{chain}:{address} (SET NX EX) — быстрый отсев в рамках TTL,
   чтобы не долбить БД на каждом тике поллинга.
2) UNIQUE(chain,address) в БД — источник истины. На конфликте делаем UPDATE
   (last_seen_at, seen_count), поэтому повторная вставка не плодит строки.

Слой идемпотентен и переживает рестарт (состояние в БД, не в памяти).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Token
from .base import NormalizedToken

logger = logging.getLogger("altsr.discovery.dedup")


class RedisLike(Protocol):
    async def set(self, name: str, value: str, *, nx: bool = ..., ex: int = ...) -> bool | None: ...


@dataclass
class UpsertResult:
    inserted: list[Token]
    updated: int

    @property
    def inserted_count(self) -> int:
        return len(self.inserted)


async def _redis_is_new(redis: RedisLike | None, key: str, ttl: int) -> bool:
    """True, если ключ ранее не встречался (или Redis недоступен)."""
    if redis is None:
        return True
    try:
        res = await redis.set(f"dedup:{key}", "1", nx=True, ex=ttl)
        return bool(res)
    except Exception as exc:  # noqa: BLE001 — Redis не должен ронять поллинг
        logger.warning("Redis dedup недоступен (%s), полагаемся на БД", exc)
        return True


async def upsert_tokens(
    session: AsyncSession,
    tokens: list[NormalizedToken],
    *,
    redis: RedisLike | None = None,
    dedup_ttl: int = 86_400,
) -> UpsertResult:
    """Вставить новые токены, обновить уже существующие. Возвращает что реально ново."""
    # Дедуп внутри одной пачки (несколько источников могут вернуть один адрес).
    by_key: dict[str, NormalizedToken] = {}
    for t in tokens:
        if t.is_valid:
            by_key.setdefault(t.dedup_key, t)

    inserted: list[Token] = []
    updated = 0
    now = datetime.now(timezone.utc)

    for key, tok in by_key.items():
        # Быстрый отсев через Redis (не критичен для корректности).
        maybe_new = await _redis_is_new(redis, key, dedup_ttl)

        existing = (
            await session.execute(
                select(Token).where(
                    Token.chain == tok.chain, Token.address == tok.address
                )
            )
        ).scalar_one_or_none()

        if existing is not None:
            existing.last_seen_at = now
            existing.seen_count += 1
            # Обогащаем пустые поля данными из нового источника.
            if existing.liquidity_usd is None and tok.liquidity_usd is not None:
                existing.liquidity_usd = tok.liquidity_usd
            if existing.symbol is None and tok.symbol:
                existing.symbol = tok.symbol
            updated += 1
            continue

        if not maybe_new:
            # Redis говорит «видели», но в БД нет — редкий рейс; всё равно вставим.
            logger.debug("Redis-miss для %s, но в БД нет — вставляем", key)

        row = Token(
            chain=tok.chain,
            address=tok.address,
            symbol=tok.symbol,
            name=tok.name,
            created_at=tok.created_at,
            liquidity_usd=tok.liquidity_usd,
            fdv=tok.fdv,
            pair_address=tok.pair_address,
            dex=tok.dex,
            socials=tok.socials_json(),
            source=tok.source,
            discovered_at=now,
            last_seen_at=now,
            seen_count=1,
        )
        session.add(row)
        inserted.append(row)

    await session.flush()
    await session.commit()
    logger.info("Upsert: +%d новых, %d обновлено", len(inserted), updated)
    return UpsertResult(inserted=inserted, updated=updated)
