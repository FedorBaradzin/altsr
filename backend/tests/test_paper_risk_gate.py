"""Stage B: Risk Engine как единый гейт бумажного входа.

Проверяем, что гейт реально встроен: сценарий, который проходит старые ad-hoc проверки
(хватает кэша, есть сигнал), но нарушает лимит Risk Engine (размер позиции относительно
equity), приводит к отказу во входе.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.config import get_settings
from app.db import create_all, get_sessionmaker
from app.discovery.base import NormalizedToken
from app.discovery.dedup import upsert_tokens
from app.models import PaperPosition, Signal
from app.paper.executor import (
    get_or_create_account,
    open_from_signals,
    paper_risk_policy,
)


def _price_fn(value):
    async def get_price(_chain, _address):
        return value
    return get_price


async def _seed_signal(address="0xtokenabc", chain="ethereum", confidence=0.8):
    async with get_sessionmaker()() as s:
        res = await upsert_tokens(s, [
            NormalizedToken(chain=chain, address=address, source="t", symbol="PEPE2")
        ])
        token = res.inserted[0]
        s.add(Signal(token_id=token.id, chain=chain, address=address, side="BUY",
                     confidence=confidence, reasons="[]", venues="[]", status="new",
                     created_at=datetime.now(timezone.utc)))
        await s.commit()
        return token.id


def test_paper_policy_maps_settings():
    s = get_settings()
    p = paper_risk_policy(s)
    assert p.version == "paper-v1"
    assert p.max_open_positions == s.paper_max_positions
    # В paper safety/рыночные гейты выключены (проверены выше по конвейеру).
    assert p.enforce_safety is False
    assert p.enforce_market_data is False


async def test_entry_blocked_when_equity_too_low_for_position_size():
    """Кэша хватает на сделку, но позиция = слишком большая доля equity → Risk Engine BLOCK."""
    await create_all()
    await _seed_signal()
    s = get_settings()
    now = datetime.now(timezone.utc)

    async with get_sessionmaker()() as sess:
        acc = await get_or_create_account(sess, s)
        # equity ≈ 1000; позиция 500 = 50% equity ≫ лимита размера позиции (2%).
        acc.cash = 1000.0
        await sess.flush()
        opened = await open_from_signals(sess, s, _price_fn(1.0), now)
        await sess.commit()

    # Кэша (1000) ХВАТАЛО на позицию (500) — без Risk Engine вход бы открылся.
    assert opened == 0
    async with get_sessionmaker()() as sess:
        positions = (await sess.execute(select(PaperPosition))).scalars().all()
        assert positions == []


async def test_entry_allowed_when_equity_healthy():
    """Контроль: при нормальном equity тот же вход проходит."""
    await create_all()
    await _seed_signal()
    s = get_settings()
    now = datetime.now(timezone.utc)
    async with get_sessionmaker()() as sess:
        opened = await open_from_signals(sess, s, _price_fn(1.0), now)
        await sess.commit()
    assert opened == 1
