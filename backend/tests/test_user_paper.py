"""Персональный бумажный счёт: open → buy → close → reset, изоляция по пользователю."""
from __future__ import annotations

import httpx
import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport

from app.auth.tokens import issue_token
from app.config import get_settings
from app.db import get_sessionmaker
from app.models import User


@pytest.fixture
async def client():
    from app.main import app

    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def _mk_user(subject: str) -> int:
    async with get_sessionmaker()() as s:
        u = User(auth_method="google", subject=subject, email=f"{subject}@x.com", display_name=subject)
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u.id


def _auth(uid: int) -> dict:
    return {"Authorization": "Bearer " + issue_token(uid, get_settings().jwt_secret, 24)}


async def test_requires_auth(client):
    r = await client.get("/api/paper/me")
    assert r.status_code == 401


async def test_open_buy_close_reset(client):
    uid = await _mk_user("alice")
    h = _auth(uid)

    # нет счёта
    r = await client.get("/api/paper/me", headers=h)
    assert r.status_code == 200 and r.json()["opened"] is False

    # открыть c $1000
    r = await client.post("/api/paper/me/open", headers=h, json={"start_balance": 1000})
    body = r.json()
    assert body["opened"] is True and body["cash"] == 1000 and body["equity"] == 1000

    # купить на $250
    r = await client.post("/api/paper/me/buy", headers=h, json={"symbol": "DORA", "chain": "base", "amount_usd": 250})
    body = r.json()
    assert body["cash"] == 750
    assert len(body["positions"]) == 1
    pos_id = body["positions"][0]["id"]
    assert body["positions"][0]["symbol"] == "DORA"

    # перебор по балансу — отказ
    r = await client.post("/api/paper/me/buy", headers=h, json={"symbol": "X", "amount_usd": 99999})
    assert r.status_code == 400

    # закрыть позицию → уходит в историю
    r = await client.post(f"/api/paper/me/close/{pos_id}", headers=h)
    body = r.json()
    assert len(body["positions"]) == 0
    assert len(body["trades"]) == 1
    assert body["win_rate"] in (0, 100)

    # reset
    r = await client.post("/api/paper/me/reset", headers=h)
    assert r.json()["opened"] is False


async def test_isolation_between_users(client):
    a = await _mk_user("ua")
    b = await _mk_user("ub")
    await client.post("/api/paper/me/open", headers=_auth(a), json={"start_balance": 500})
    await client.post("/api/paper/me/buy", headers=_auth(a), json={"symbol": "AA", "amount_usd": 100})

    # у b счёта нет
    r = await client.get("/api/paper/me", headers=_auth(b))
    assert r.json()["opened"] is False

    # a видит свою позицию
    r = await client.get("/api/paper/me", headers=_auth(a))
    assert len(r.json()["positions"]) == 1 and r.json()["cash"] == 400
