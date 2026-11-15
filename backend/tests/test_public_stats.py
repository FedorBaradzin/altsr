"""Публичная статистика бумажного счёта владельца (без авторизации)."""
from __future__ import annotations

import httpx
import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport

from app.config import get_settings
from app.db import get_sessionmaker
from app.models import User, UserPaperAccount


@pytest.fixture
async def client():
    from app.main import app
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def test_public_paper_no_owner(client, monkeypatch):
    # нет ADMIN_IDENTIFIERS → opened:False, 200 (не падает)
    s = get_settings()
    monkeypatch.setattr(type(s), "admin_identifier_list", property(lambda self: []))
    r = await client.get("/api/public/paper")
    assert r.status_code == 200
    assert r.json()["opened"] is False


async def test_public_paper_returns_owner_summary(client, monkeypatch):
    async with get_sessionmaker()() as sess:
        u = User(auth_method="google", subject="owner-pub", email="owner-pub@x.com", tier="pro")
        sess.add(u); await sess.commit(); await sess.refresh(u)
        acc = UserPaperAccount(user_id=u.id, start_balance=5000.0, cash=5000.0)
        sess.add(acc); await sess.commit()
    s = get_settings()
    monkeypatch.setattr(type(s), "admin_identifier_list",
                        property(lambda self: ["owner-pub@x.com"]))
    r = await client.get("/api/public/paper")
    assert r.status_code == 200
    j = r.json()
    assert j["opened"] is True
    assert j["start"] == 5000
    assert j["open_positions"] == 0
    assert j["closed"] == 0
    assert "equity" in j and "win_rate" in j and "realized_pnl" in j
