"""Telegram-привязка: webhook /start связывает chat_id, секрет проверяется."""
from __future__ import annotations

import httpx
import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport

from app.api.telegram import webhook_secret
from app.auth.tokens import issue_token
from app.config import get_settings
from app.db import get_sessionmaker
from app.models import TelegramLinkCode, User


@pytest.fixture
async def client():
    from app.main import app
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def _mk_user(subject: str, tier: str = "free") -> int:
    async with get_sessionmaker()() as s:
        u = User(auth_method="google", subject=subject, email=f"{subject}@x.com", tier=tier)
        s.add(u); await s.commit(); await s.refresh(u)
        return u.id


def _auth(uid: int) -> dict:
    return {"Authorization": "Bearer " + issue_token(uid, get_settings().jwt_secret, 24)}


async def test_status_and_webhook_link(client):
    uid = await _mk_user("tg1")
    h = _auth(uid)

    r = await client.get("/api/telegram/status", headers=h)
    assert r.json()["linked"] is False

    # завести код привязки напрямую (как делает /link)
    async with get_sessionmaker()() as s:
        s.add(TelegramLinkCode(code="abc123", user_id=uid)); await s.commit()

    secret = webhook_secret(get_settings())
    update = {"message": {"text": "/start abc123", "chat": {"id": 55501}}}
    # неверный секрет → 403
    bad = await client.post("/api/telegram/webhook", json=update,
                            headers={"X-Telegram-Bot-Api-Secret-Token": "nope"})
    assert bad.status_code == 403

    # верный секрет → привязка
    ok = await client.post("/api/telegram/webhook", json=update,
                           headers={"X-Telegram-Bot-Api-Secret-Token": secret})
    assert ok.status_code == 200

    r = await client.get("/api/telegram/status", headers=h)
    assert r.json()["linked"] is True

    async with get_sessionmaker()() as s:
        u = (await s.get(User, uid))
        assert u.tg_chat_id == "55501"

    # unlink
    r = await client.post("/api/telegram/unlink", headers=h)
    assert r.json()["linked"] is False


async def test_link_gated_to_autonomous(client, monkeypatch):
    """Личная привязка Telegram: Free/Pro → 402, Autonomous → разрешено."""
    from app.api import telegram as tg
    from app.config import get_settings as gs
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    gs.cache_clear()

    async def fake_name(settings):
        return "TestBot"
    monkeypatch.setattr(tg, "_bot_name", fake_name)

    free = await _mk_user("tg_free", "free")
    r = await client.post("/api/telegram/link", headers=_auth(free))
    assert r.status_code == 402, r.text

    pro = await _mk_user("tg_pro", "pro")
    r = await client.post("/api/telegram/link", headers=_auth(pro))
    assert r.status_code == 402, r.text

    au = await _mk_user("tg_auto", "autonomous")
    r = await client.post("/api/telegram/link", headers=_auth(au))
    assert r.status_code == 200, r.text
    assert "t.me/TestBot" in r.json()["url"]
    gs.cache_clear()


async def test_webhook_unknown_code_is_noop(client):
    secret = webhook_secret(get_settings())
    update = {"message": {"text": "/start ghost", "chat": {"id": 999}}}
    r = await client.post("/api/telegram/webhook", json=update,
                          headers={"X-Telegram-Bot-Api-Secret-Token": secret})
    assert r.status_code == 200 and r.json()["ok"] is True
