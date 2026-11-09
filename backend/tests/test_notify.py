"""Нотификатор: формат алерта + Telegram (no-op без конфига, respx с конфигом)."""
from __future__ import annotations

import httpx
import respx

from app.config import get_settings
from app.notify.format import format_buy_alert
from app.notify.telegram import TelegramNotifier
from app.signals.venues import build_buy_options


def test_format_contains_links_and_disclaimer():
    opts = build_buy_options("solana", "So1Mint", None)
    msg = format_buy_alert(
        chain="solana", address="So1Mint", symbol="BONKJR", name="Bonk Jr",
        confidence=0.82, risk_score=8, reasons=["safety PASS (risk 8)", "ликвидность $9,000 ≥ $5,000"],
        liquidity_usd=9000.0, buy_options=opts,
    )
    assert "BUY-сигнал" in msg
    assert "BONKJR" in msg
    assert "Где и как купить" in msg
    assert "jup.ag" in msg
    assert "Не инвест-рекомендация" in msg


async def test_notifier_noop_without_config():
    n = TelegramNotifier(get_settings())
    assert n.enabled is False
    assert await n.send("hi") is False


@respx.mock(assert_all_called=True)
async def test_notifier_sends_with_config(respx_mock):
    s = get_settings()
    s.telegram_bot_token = "T0KEN"
    s.telegram_chat_id = "123"
    route = respx_mock.post(f"{s.telegram_api_base}/botT0KEN/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    n = TelegramNotifier(s)
    assert n.enabled is True
    assert await n.send("<b>hi</b>") is True
    assert route.called
