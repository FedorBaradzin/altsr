"""Дедуп: повторные прогоны не плодят строки (критерий приёмки Фазы 0)."""
from __future__ import annotations

from sqlalchemy import func, select

from app.discovery.base import NormalizedToken
from app.discovery.dedup import upsert_tokens
from app.models import Token


def _tok(address="0xabc", chain="ethereum", **kw):
    return NormalizedToken(chain=chain, address=address, source="test", **kw)


async def test_insert_then_dedup_same_batch(session):
    tokens = [_tok(symbol="A"), _tok(symbol="A-dup"), _tok(address="0xdef", symbol="B")]
    res = await upsert_tokens(session, tokens)
    # Два уникальных адреса из трёх записей.
    assert res.inserted_count == 2
    total = (await session.execute(select(func.count()).select_from(Token))).scalar_one()
    assert total == 2


async def test_second_run_updates_not_inserts(session):
    await upsert_tokens(session, [_tok(symbol="A")])
    res2 = await upsert_tokens(session, [_tok(symbol="A")])
    assert res2.inserted_count == 0
    assert res2.updated == 1

    row = (await session.execute(select(Token))).scalar_one()
    assert row.seen_count == 2  # счётчик вырос, строка одна
    total = (await session.execute(select(func.count()).select_from(Token))).scalar_one()
    assert total == 1


async def test_case_insensitive_address_dedup(session):
    await upsert_tokens(session, [_tok(address="0xAbC")])
    res = await upsert_tokens(session, [_tok(address="0xabc")])
    assert res.inserted_count == 0
    assert res.updated == 1


async def test_enrichment_fills_empty_fields(session):
    await upsert_tokens(session, [_tok(symbol=None, liquidity_usd=None)])
    await upsert_tokens(session, [_tok(symbol="LATE", liquidity_usd=1000.0)])
    row = (await session.execute(select(Token))).scalar_one()
    assert row.symbol == "LATE"
    assert row.liquidity_usd == 1000.0


async def test_redis_layer_does_not_break_correctness(session, fake_redis):
    r1 = await upsert_tokens(session, [_tok()], redis=fake_redis, dedup_ttl=60)
    assert r1.inserted_count == 1
    # Redis-ключ уже стоит, но БД — источник истины: апдейт, не дубль.
    r2 = await upsert_tokens(session, [_tok()], redis=fake_redis, dedup_ttl=60)
    assert r2.inserted_count == 0
    assert r2.updated == 1
