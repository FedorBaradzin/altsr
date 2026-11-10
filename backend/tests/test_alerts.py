"""Системные алерты о поломках → Telegram, с дедупом (не спамить одинаковым)."""
from __future__ import annotations

import httpx
import respx

from app.config import get_settings
from app.notify.alerts import SystemAlerter, format_system_alert


def _tg_settings():
    s = get_settings()
    s.telegram_bot_token = "T0KEN"
    s.telegram_chat_id = "123"
    return s


def test_format_contains_code_and_message():
    msg = format_system_alert("birdeye_credits", "Нужно пополнить Birdeye", severity="error")
    assert "birdeye_credits" in msg
    assert "Нужно пополнить Birdeye" in msg


@respx.mock(assert_all_called=True)
async def test_alert_sends_to_telegram(respx_mock, fake_redis):
    s = _tg_settings()
    route = respx_mock.post(f"{s.telegram_api_base}/botT0KEN/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    alerter = SystemAlerter(s, redis=fake_redis)
    sent = await alerter.alert("worker_down", "discovery упал")
    assert sent is True
    assert route.called


@respx.mock(assert_all_called=False)
async def test_alert_dedups_same_code_within_window(respx_mock, fake_redis):
    s = _tg_settings()
    route = respx_mock.post(f"{s.telegram_api_base}/botT0KEN/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    alerter = SystemAlerter(s, redis=fake_redis)
    first = await alerter.alert("birdeye_credits", "пополни", dedup_seconds=3600)
    second = await alerter.alert("birdeye_credits", "пополни", dedup_seconds=3600)
    assert first is True
    assert second is False               # второй подавлён дедупом
    assert route.call_count == 1


@respx.mock(assert_all_called=False)
async def test_alert_different_codes_both_sent(respx_mock, fake_redis):
    s = _tg_settings()
    route = respx_mock.post(f"{s.telegram_api_base}/botT0KEN/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    alerter = SystemAlerter(s, redis=fake_redis)
    await alerter.alert("birdeye_credits", "a")
    await alerter.alert("worker_down", "b")
    assert route.call_count == 2


async def test_alert_noop_without_telegram_config(fake_redis):
    alerter = SystemAlerter(get_settings(), redis=fake_redis)  # нет токена/чата
    assert await alerter.alert("x", "y") is False
