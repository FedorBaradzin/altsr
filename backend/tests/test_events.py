"""Шина доменных событий (T8): эмиссия в Redis pub/sub, дедуп, дайджест, тихие часы."""
from __future__ import annotations

import json

import httpx
import respx

from app.config import get_settings
from app.notify.events import (
    CHANNEL_PREFIX,
    DigestCollector,
    EquityTick,
    Event,
    RuleFired,
    SignalEvent,
    StageEvent,
    TradeEvent,
    build_digest,
    in_quiet_hours,
    publish,
)
from app.notify.telegram import notify_digest


async def _publish_and_capture(redis, event) -> tuple[bool, dict | None]:
    """Подписаться на канал события, опубликовать его и вернуть (ok, payload-dict).

    Подписка аккуратно закрывается, чтобы не оставлять висящих pub/sub-соединений
    между тестами.
    """
    import asyncio

    pubsub = redis.pubsub()
    await pubsub.subscribe(event.channel)
    try:
        ok = await publish(redis, event)
        for _ in range(50):
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.05)
            if msg is not None:
                return ok, json.loads(msg["data"])
            await asyncio.sleep(0.01)
        return ok, None
    finally:
        await pubsub.unsubscribe(event.channel)
        await pubsub.aclose()


# --- Каждое доменное событие публикуется ровно один раз -----------------------


async def test_equity_tick_publishes_once(fake_redis):
    ev = EquityTick(equity_usd=101_000.0, balance_usd=99_000.0, open_positions=3)
    ok, payload = await _publish_and_capture(fake_redis, ev)
    assert ok is True
    assert payload is not None
    assert payload["type"] == "equity_tick"
    assert payload["equity_usd"] == 101_000.0
    assert payload["open_positions"] == 3


async def test_stage_event_publishes_once(fake_redis):
    ev = StageEvent(chain="solana", address="So1Mint", symbol="BONK", stage="entered")
    ok, payload = await _publish_and_capture(fake_redis, ev)
    assert ok is True
    assert payload is not None
    assert payload["type"] == "stage"
    assert payload["stage"] == "entered"
    assert payload["chain"] == "solana"


async def test_trade_event_publishes_once(fake_redis):
    ev = TradeEvent(chain="eth", address="0xabc", action="open", size_usd=500.0, trade_id="t-1")
    ok, payload = await _publish_and_capture(fake_redis, ev)
    assert ok is True
    assert payload is not None
    assert payload["type"] == "trade"
    assert payload["action"] == "open"
    assert payload["trade_id"] == "t-1"


async def test_rule_fired_publishes_once(fake_redis):
    ev = RuleFired(rule="trailing_stop", chain="base", address="0xdef", detail="−8% от пика")
    ok, payload = await _publish_and_capture(fake_redis, ev)
    assert ok is True
    assert payload is not None
    assert payload["type"] == "rule_fired"
    assert payload["rule"] == "trailing_stop"


async def test_signal_event_publishes_once(fake_redis):
    ev = SignalEvent(
        chain="solana", address="So1Mint", symbol="BONK", confidence=0.82, risk_score=8
    )
    ok, payload = await _publish_and_capture(fake_redis, ev)
    assert ok is True
    assert payload is not None
    assert payload["type"] == "signal"
    assert payload["confidence"] == 0.82
    assert payload["risk_score"] == 8


async def test_channel_name_matches_type(fake_redis):
    ev = SignalEvent(chain="solana", address="X")
    assert ev.channel == CHANNEL_PREFIX + "signal"


# --- Дедуп: одно и то же событие не публикуется дважды ------------------------


async def test_dedup_prevents_duplicate(fake_redis):
    ev = SignalEvent(chain="solana", address="So1Mint")
    first = await publish(fake_redis, ev, dedup_seconds=300)
    second = await publish(fake_redis, ev, dedup_seconds=300)
    assert first is True
    assert second is False  # второй подавлён дедупом


async def test_dedup_different_identity_both_publish(fake_redis):
    a = SignalEvent(chain="solana", address="MintA")
    b = SignalEvent(chain="solana", address="MintB")
    assert await publish(fake_redis, a, dedup_seconds=300) is True
    assert await publish(fake_redis, b, dedup_seconds=300) is True


async def test_no_dedup_when_disabled(fake_redis):
    ev = StageEvent(chain="eth", address="0x1", stage="screened")
    assert await publish(fake_redis, ev, dedup_seconds=0) is True
    assert await publish(fake_redis, ev, dedup_seconds=0) is True  # дедуп выключен


async def test_publish_without_redis_returns_false():
    ev = SignalEvent(chain="solana", address="X")
    assert await publish(None, ev) is False


# --- Тихие часы --------------------------------------------------------------


def test_quiet_hours_overnight_window():
    # Окно 23..8 (через полночь).
    assert in_quiet_hours(23, 23, 8) is True
    assert in_quiet_hours(2, 23, 8) is True
    assert in_quiet_hours(7, 23, 8) is True
    assert in_quiet_hours(8, 23, 8) is False  # конец не включается
    assert in_quiet_hours(12, 23, 8) is False
    assert in_quiet_hours(22, 23, 8) is False


def test_quiet_hours_same_day_window():
    # Обычное окно 1..5.
    assert in_quiet_hours(1, 1, 5) is True
    assert in_quiet_hours(4, 1, 5) is True
    assert in_quiet_hours(5, 1, 5) is False
    assert in_quiet_hours(0, 1, 5) is False


def test_quiet_hours_empty_window():
    # start == end → тихих часов нет.
    assert in_quiet_hours(0, 8, 8) is False
    assert in_quiet_hours(8, 8, 8) is False


# --- Дайджест ----------------------------------------------------------------


def test_build_digest_collects_window_events():
    events: list[Event] = [
        SignalEvent(chain="solana", address="A"),
        SignalEvent(chain="solana", address="B"),
        TradeEvent(chain="eth", address="0x1", action="open", size_usd=500.0),
        TradeEvent(chain="eth", address="0x1", action="close", pnl_usd=120.0, trade_id="t2"),
        RuleFired(rule="trailing_stop", chain="eth", address="0x1"),
    ]
    text = build_digest(events)
    assert "Всего событий: 5" in text
    assert "Сигналов (BUY): 2" in text
    assert "Сделок: 2" in text
    assert "120.00" in text  # реализованный PnL
    assert "trailing_stop" in text


def test_build_digest_empty():
    assert "событий не было" in build_digest([])


def test_digest_collector_buffers_and_flushes():
    c = DigestCollector()
    c.add(SignalEvent(chain="solana", address="A"))
    c.add(TradeEvent(chain="eth", address="0x1", action="open"))
    assert len(c) == 2
    assert len(c.pending) == 2
    flushed = c.flush()
    assert len(flushed) == 2
    assert len(c) == 0  # буфер очищен


def test_digest_collector_build_and_flush():
    c = DigestCollector()
    c.add(SignalEvent(chain="solana", address="A"))
    text = c.build_and_flush()
    assert "Всего событий: 1" in text
    assert len(c) == 0


# --- Тонкий Telegram-хук (за флагом) -----------------------------------------


async def test_notify_digest_noop_when_disabled():
    s = get_settings()
    s.telegram_bot_token = "T0KEN"
    s.telegram_chat_id = "123"
    # eventbus_enabled по умолчанию False → no-op
    assert s.eventbus_enabled is False
    assert await notify_digest(s, "дайджест") is False


@respx.mock(assert_all_called=True)
async def test_notify_digest_sends_when_enabled(respx_mock):
    s = get_settings()
    s.eventbus_enabled = True
    s.telegram_bot_token = "T0KEN"
    s.telegram_chat_id = "123"
    route = respx_mock.post(f"{s.telegram_api_base}/botT0KEN/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    assert await notify_digest(s, "<b>дайджест</b>") is True
    assert route.called
