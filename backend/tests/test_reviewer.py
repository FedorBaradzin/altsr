"""Reviewer-стадия (T6): чистые агрегаты + Redis-блеклист + ревью закрытой сделки.

БД не нужна для агрегатов. Redis — fakeredis (fixture fake_redis).
Executor-гейт проверяем на реальной бумажной позиции (sqlite in-memory).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.config import get_settings
from app.db import create_all, get_sessionmaker
from app.discovery.base import NormalizedToken
from app.discovery.dedup import upsert_tokens
from app.models import PaperPosition, Signal
from app.paper.executor import open_from_signals
from app.paper.reviewer import (
    TradeResult,
    avg_r,
    blacklist_token,
    is_blacklisted,
    max_drawdown,
    net_pnl,
    review_closed_trade,
    win_rate,
)

# --- Фикстуры результатов (знаковые значения считаются вручную) -------------
_RESULTS = [
    TradeResult(pnl_usd=100.0, r_multiple=2.0, net_after_costs=95.0, exit_reason="take profit"),
    TradeResult(pnl_usd=-50.0, r_multiple=-1.0, net_after_costs=-55.0, exit_reason="hard stop"),
    TradeResult(pnl_usd=200.0, r_multiple=3.0, net_after_costs=190.0, exit_reason="trailing"),
    TradeResult(pnl_usd=-30.0, r_multiple=-0.6, net_after_costs=-33.0, exit_reason="stall"),
]


def test_trade_result_is_frozen():
    r = _RESULTS[0]
    try:
        r.pnl_usd = 1.0  # type: ignore[misc]
    except Exception:  # noqa: BLE001 — frozen dataclass бросает FrozenInstanceError
        return
    raise AssertionError("TradeResult должен быть неизменяемым (frozen)")


# --- Агрегаты ----------------------------------------------------------------
def test_win_rate():
    # Прибыльны 2 из 4 (net_after_costs > 0) → 0.5.
    assert win_rate(_RESULTS) == 0.5


def test_avg_r():
    # (2.0 - 1.0 + 3.0 - 0.6) / 4 = 0.85.
    assert abs(avg_r(_RESULTS) - 0.85) < 1e-9


def test_net_pnl():
    # 95 - 55 + 190 - 33 = 197.
    assert abs(net_pnl(_RESULTS) - 197.0) < 1e-9


def test_max_drawdown():
    # Кумулятив: 95, 40, 230, 197. Пики: 95, 95, 230, 230.
    # Просадки: 0, 55, 0, 33 → макс 55.
    assert abs(max_drawdown(_RESULTS) - 55.0) < 1e-9


def test_aggregates_empty_are_zero():
    assert win_rate([]) == 0.0
    assert avg_r([]) == 0.0
    assert net_pnl([]) == 0.0
    assert max_drawdown([]) == 0.0


def test_max_drawdown_all_up_is_zero():
    up = [
        TradeResult(pnl_usd=10.0, r_multiple=1.0, net_after_costs=10.0, exit_reason="tp"),
        TradeResult(pnl_usd=20.0, r_multiple=2.0, net_after_costs=20.0, exit_reason="tp"),
    ]
    assert max_drawdown(up) == 0.0


# --- Redis-блеклист ----------------------------------------------------------
async def test_blacklist_roundtrip(fake_redis):
    assert await is_blacklisted(fake_redis, "ethereum", "0xabc") is False
    await blacklist_token(fake_redis, "ethereum", "0xabc", 3600, "hard stop")
    assert await is_blacklisted(fake_redis, "ethereum", "0xabc") is True
    # Ключ построен по схеме altsr:blacklist:{chain}:{address}.
    assert await fake_redis.get("altsr:blacklist:ethereum:0xabc") == "hard stop"


async def test_is_blacklisted_no_redis_is_false():
    assert await is_blacklisted(None, "ethereum", "0xabc") is False


async def test_blacklist_scoped_per_chain_and_address(fake_redis):
    await blacklist_token(fake_redis, "ethereum", "0xabc", 3600, "loss")
    assert await is_blacklisted(fake_redis, "solana", "0xabc") is False
    assert await is_blacklisted(fake_redis, "ethereum", "0xother") is False


# --- Ревью закрытой сделки ---------------------------------------------------
async def test_review_losing_trade_blacklists(fake_redis):
    s = get_settings().model_copy(update={"blacklist_on_loss": True})
    loss = TradeResult(pnl_usd=-40.0, r_multiple=-1.0, net_after_costs=-42.0,
                       exit_reason="hard stop")
    stats = await review_closed_trade(
        fake_redis, s, chain="ethereum", address="0xloser", result=loss,
    )
    assert stats.net_pnl < 0
    assert stats.trades == 1
    assert await is_blacklisted(fake_redis, "ethereum", "0xloser") is True


async def test_review_winning_trade_not_blacklisted(fake_redis):
    s = get_settings().model_copy(update={"blacklist_on_loss": True})
    win = TradeResult(pnl_usd=120.0, r_multiple=2.5, net_after_costs=110.0,
                      exit_reason="take profit")
    await review_closed_trade(
        fake_redis, s, chain="ethereum", address="0xwinner", result=win,
    )
    assert await is_blacklisted(fake_redis, "ethereum", "0xwinner") is False


async def test_review_respects_blacklist_off(fake_redis):
    s = get_settings().model_copy(update={"blacklist_on_loss": False})
    loss = TradeResult(pnl_usd=-40.0, r_multiple=-1.0, net_after_costs=-42.0,
                       exit_reason="hard stop")
    await review_closed_trade(
        fake_redis, s, chain="ethereum", address="0xloser", result=loss,
    )
    assert await is_blacklisted(fake_redis, "ethereum", "0xloser") is False


async def test_review_history_rolls_up(fake_redis):
    s = get_settings().model_copy(update={"blacklist_on_loss": False})
    history = _RESULTS[:3]
    stats = await review_closed_trade(
        fake_redis, s, chain="ethereum", address="0xt", result=_RESULTS[3],
        history=history,
    )
    assert stats.trades == 4
    assert abs(stats.net_pnl - 197.0) < 1e-9
    assert stats.win_rate == 0.5


# --- Гейт повторного входа в executor ----------------------------------------
async def _seed_signal(address: str, chain: str = "ethereum") -> int:
    async with get_sessionmaker()() as sess:
        res = await upsert_tokens(sess, [
            NormalizedToken(chain=chain, address=address, source="t", symbol="SYM")
        ])
        token = res.inserted[0]
        sess.add(Signal(token_id=token.id, chain=chain, address=address, side="BUY",
                        confidence=0.8, reasons="[]", venues="[]", status="new",
                        created_at=datetime.now(timezone.utc)))
        await sess.commit()
        return token.id


def _price_fn(value):
    async def get_price(_chain, _address):
        return value
    return get_price


async def test_blacklisted_token_not_reentered(fake_redis):
    await create_all()
    await _seed_signal("0xbanned")
    s = get_settings().model_copy(update={"reviewer_enabled": True})
    now = datetime.now(timezone.utc)
    await blacklist_token(fake_redis, "ethereum", "0xbanned", 3600, "hard stop")
    async with get_sessionmaker()() as sess:
        opened = await open_from_signals(sess, s, _price_fn(1.0), now, redis=fake_redis)
        await sess.commit()
    assert opened == 0
    async with get_sessionmaker()() as sess:
        rows = (await sess.execute(select(PaperPosition))).scalars().all()
        assert rows == []


async def test_non_blacklisted_token_reentered(fake_redis):
    await create_all()
    await _seed_signal("0xclean")
    s = get_settings().model_copy(update={"reviewer_enabled": True})
    now = datetime.now(timezone.utc)
    async with get_sessionmaker()() as sess:
        opened = await open_from_signals(sess, s, _price_fn(1.0), now, redis=fake_redis)
        await sess.commit()
    assert opened == 1


async def test_gate_disabled_when_reviewer_off(fake_redis):
    # reviewer_enabled=False (по умолчанию) → блеклист игнорируется, поведение прежнее.
    await create_all()
    await _seed_signal("0xbanned")
    s = get_settings()  # reviewer_enabled по умолчанию False
    now = datetime.now(timezone.utc)
    await blacklist_token(fake_redis, "ethereum", "0xbanned", 3600, "hard stop")
    async with get_sessionmaker()() as sess:
        opened = await open_from_signals(sess, s, _price_fn(1.0), now, redis=fake_redis)
        await sess.commit()
    assert opened == 1
