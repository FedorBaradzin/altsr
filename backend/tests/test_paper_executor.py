"""Executor: открытие по сигналу, выходы, частичный TP, дневной лимит."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import get_settings
from app.db import create_all, get_sessionmaker
from app.discovery.base import NormalizedToken
from app.discovery.dedup import upsert_tokens
from app.models import PaperAccount, PaperPosition, Signal
from app.paper.executor import (
    get_or_create_account,
    open_from_signals,
    process_positions,
)


def _price_fn(value):
    async def get_price(_chain, _address):
        return value
    return get_price


async def _seed_signal(address="0xtokenabc", chain="ethereum"):
    async with get_sessionmaker()() as s:
        res = await upsert_tokens(s, [
            NormalizedToken(chain=chain, address=address, source="t", symbol="PEPE2")
        ])
        token = res.inserted[0]
        s.add(Signal(token_id=token.id, chain=chain, address=address, side="BUY",
                     confidence=0.95, reasons="[]", venues="[]", status="new",
                     created_at=datetime.now(timezone.utc)))
        await s.commit()
        return token.id


async def test_open_from_signal():
    await create_all()
    await _seed_signal()
    s = get_settings()
    now = datetime.now(timezone.utc)
    async with get_sessionmaker()() as sess:
        opened = await open_from_signals(sess, s, _price_fn(1.0), now)
        await sess.commit()
    assert opened == 1
    async with get_sessionmaker()() as sess:
        acc = await get_or_create_account(sess, s)
        assert acc.cash == s.paper_start_balance - s.paper_position_size_usd
        pos = (await sess.execute(select(PaperPosition))).scalar_one()
        assert pos.status == "open" and pos.entry_price == 1.0


async def test_hard_stop_closes_with_loss():
    await create_all()
    await _seed_signal()
    s = get_settings()
    now = datetime.now(timezone.utc)
    async with get_sessionmaker()() as sess:
        await open_from_signals(sess, s, _price_fn(1.0), now)
        # Цена падает ниже hard stop (0.75).
        closed = await process_positions(sess, s, _price_fn(0.70), now)
        await sess.commit()
    assert closed == 1
    async with get_sessionmaker()() as sess:
        pos = (await sess.execute(select(PaperPosition))).scalar_one()
        assert pos.status == "closed"
        assert "hard stop" in pos.exit_reason
        assert pos.realized_pnl_usd < 0


async def test_partial_take_profit():
    await create_all()
    await _seed_signal()
    s = get_settings()
    now = datetime.now(timezone.utc)
    async with get_sessionmaker()() as sess:
        await open_from_signals(sess, s, _price_fn(1.0), now)
        closed = await process_positions(sess, s, _price_fn(2.0), now)  # 2x → partial
        await sess.commit()
    assert closed == 0
    async with get_sessionmaker()() as sess:
        pos = (await sess.execute(select(PaperPosition))).scalar_one()
        assert pos.tp_taken is True
        assert abs(pos.remaining_fraction - 0.3) < 1e-9  # tp_fraction 0.7 → остаток 0.3
        assert pos.realized_pnl_usd > 0  # зафиксировали прибыль на части


async def test_flat_price_holds_but_costs_nothing_until_exit():
    await create_all()
    await _seed_signal()
    s = get_settings()
    now = datetime.now(timezone.utc)
    async with get_sessionmaker()() as sess:
        await open_from_signals(sess, s, _price_fn(1.0), now)
        closed = await process_positions(sess, s, _price_fn(1.0), now)
        await sess.commit()
    assert closed == 0  # флэт удерживается


async def test_stall_closes():
    await create_all()
    await _seed_signal()
    s = get_settings()
    now = datetime.now(timezone.utc)
    async with get_sessionmaker()() as sess:
        await open_from_signals(sess, s, _price_fn(1.0), now)
        pos = (await sess.execute(select(PaperPosition))).scalar_one()
        pos.last_high_at = now - timedelta(minutes=s.paper_stall_minutes + 1)
        await sess.flush()
        closed = await process_positions(sess, s, _price_fn(1.0), now)
        await sess.commit()
    assert closed == 1


async def test_daily_loss_limit_halts_opening():
    await create_all()
    s = get_settings()
    now = datetime.now(timezone.utc)
    # Закрытая сегодня позиция с большим убытком.
    async with get_sessionmaker()() as sess:
        await get_or_create_account(sess, s)
        res = await upsert_tokens(sess, [
            NormalizedToken(chain="ethereum", address="0xloser", source="t")
        ])
        tid = res.inserted[0].id
        sess.add(PaperPosition(
            token_id=tid, chain="ethereum", address="0xloser", status="closed",
            size_usd=100, entry_price=1.0, peak_price=1.0, last_price=0.1,
            remaining_fraction=0.0, realized_pnl_usd=-(s.paper_daily_loss_limit_usd + 50),
            opened_at=now, last_high_at=now, closed_at=now,
        ))
        await sess.commit()

    await _seed_signal(address="0xnewone")
    async with get_sessionmaker()() as sess:
        opened = await open_from_signals(sess, s, _price_fn(1.0), now)
        await sess.commit()
    assert opened == 0  # лимит убытка → покупки остановлены


# ---------- Анти-скам гейт входа (safety verdict) ----------

async def _seed_signal_with_verdict(verdict, address, chain="solana"):
    from app.models import SafetyReport
    async with get_sessionmaker()() as s:
        res = await upsert_tokens(s, [
            NormalizedToken(chain=chain, address=address, source="t", symbol="GATE")
        ])
        token = res.inserted[0]
        s.add(Signal(token_id=token.id, chain=chain, address=address, side="BUY",
                     confidence=0.9, reasons="[]", venues="[]", status="new",
                     created_at=datetime.now(timezone.utc)))
        if verdict is not None:
            s.add(SafetyReport(token_id=token.id, chain=chain, address=address,
                               risk_score=90 if verdict == "BLOCK" else 50,
                               verdict=verdict, created_at=datetime.now(timezone.utc)))
        await s.commit()
        return token.id


async def test_gate_blocks_block_verdict():
    await create_all()
    await _seed_signal_with_verdict("BLOCK", "BlockMintGate1111111111111111111111111111")
    s = get_settings()
    async with get_sessionmaker()() as sess:
        opened = await open_from_signals(sess, s, _price_fn(1.0), datetime.now(timezone.utc))
        await sess.commit()
    assert opened == 0


async def test_gate_blocks_review_verdict_by_default():
    await create_all()
    await _seed_signal_with_verdict("REVIEW", "ReviewMintGate111111111111111111111111111")
    s = get_settings()
    async with get_sessionmaker()() as sess:
        opened = await open_from_signals(sess, s, _price_fn(1.0), datetime.now(timezone.utc))
        await sess.commit()
    assert opened == 0


async def test_gate_allows_pass_verdict():
    await create_all()
    await _seed_signal_with_verdict("PASS", "PassMintGate11111111111111111111111111111")
    s = get_settings()
    async with get_sessionmaker()() as sess:
        opened = await open_from_signals(sess, s, _price_fn(1.0), datetime.now(timezone.utc))
        await sess.commit()
    assert opened == 1


async def test_gate_allows_unscreened_token():
    # Нет отчёта (None) → вход разрешён, движок не глохнет на несканированных.
    await create_all()
    await _seed_signal_with_verdict(None, "NoReportGate11111111111111111111111111111")
    s = get_settings()
    async with get_sessionmaker()() as sess:
        opened = await open_from_signals(sess, s, _price_fn(1.0), datetime.now(timezone.utc))
        await sess.commit()
    assert opened == 1


async def test_low_confidence_signal_is_skipped():
    # Сигнал с уверенностью ниже порога (0.85) не входит.
    await create_all()
    async with get_sessionmaker()() as s:
        res = await upsert_tokens(s, [
            NormalizedToken(chain="solana", address="LowConfMint111111111111111111111111111111",
                            source="t", symbol="LOWC")
        ])
        tok = res.inserted[0]
        s.add(Signal(token_id=tok.id, chain="solana", address="LowConfMint111111111111111111111111111111",
                     side="BUY", confidence=0.70, reasons="[]", venues="[]", status="new",
                     created_at=datetime.now(timezone.utc)))
        await s.commit()
    st = get_settings()
    async with get_sessionmaker()() as sess:
        opened = await open_from_signals(sess, st, _price_fn(1.0), datetime.now(timezone.utc))
        await sess.commit()
    assert opened == 0
