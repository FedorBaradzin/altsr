"""Самопроверка Telegram: резолв chat_id из getUpdates + отправка тестового алерта."""
from __future__ import annotations

import httpx
import respx

from app.config import get_settings
from app.discovery.base import HttpClient
from app.notify.selftest import resolve_chat_ids, run


def _bot_settings():
    s = get_settings()
    s.telegram_bot_token = "BOT123"
    return s


@respx.mock(assert_all_called=True)
async def test_resolve_chat_ids_parses_getupdates(respx_mock):
    s = _bot_settings()
    respx_mock.get(f"{s.telegram_api_base}/botBOT123/getUpdates").mock(
        return_value=httpx.Response(200, json={
            "ok": True,
            "result": [
                {"message": {"chat": {"id": 555, "first_name": "Fedor"}}},
                {"message": {"chat": {"id": 555, "first_name": "Fedor"}}},   # дубль
                {"channel_post": {"chat": {"id": -100999, "title": "ALTSR Alerts"}}},
            ],
        })
    )
    async with HttpClient() as http:
        chats = await resolve_chat_ids(s, http)
    assert ("555", "Fedor") in chats
    assert ("-100999", "ALTSR Alerts") in chats
    assert len(chats) == 2   # дедуп сработал


async def test_resolve_chat_ids_empty_without_token():
    async with HttpClient() as http:
        chats = await resolve_chat_ids(get_settings(), http)
    assert chats == []


@respx.mock(assert_all_called=True)
async def test_run_sends_test_alert_when_chat_configured(respx_mock):
    s = _bot_settings()
    s.telegram_chat_id = "555"
    route = respx_mock.post(f"{s.telegram_api_base}/botBOT123/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    rc = await run()
    assert rc == 0
    assert route.called


async def test_run_returns_1_without_token():
    # get_settings() без токена → подсказка и код 1.
    assert await run() == 1
