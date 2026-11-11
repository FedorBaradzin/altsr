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


async def _mk_user(subject: str) -> int:
    async with get_sessionmaker()() as s:
        u = User(auth_method="google", subject=subject, email=f"{subject}@x.com")
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


async def test_webhook_unknown_code_is_noop(client):
    secret = webhook_secret(get_settings())
    update = {"message": {"text": "/start ghost", "chat": {"id": 999}}}
    r = await client.post("/api/telegram/webhook", json=update,
                          headers={"X-Telegram-Bot-Api-Secret-Token": secret})
    assert r.status_code == 200 and r.json()["ok"] is True
