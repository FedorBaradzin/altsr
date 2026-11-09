"""Админ-панель: доступ только админу, обзор, ручная выдача тарифа, флаги."""
from __future__ import annotations

import httpx
import pytest
from asgi_lifespan import LifespanManager
from eth_account import Account
from eth_account.messages import encode_defunct
from httpx import ASGITransport

from app.config import get_settings


@pytest.fixture
async def client():
    from app.main import app

    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def _login(client) -> tuple[str, str]:
    acct = Account.create()
    r = await client.post("/api/auth/wallet/nonce", json={"address": acct.address})
    signed = Account.sign_message(encode_defunct(text=r.json()["message"]), acct.key)
    r2 = await client.post("/api/auth/wallet/verify",
                           json={"address": acct.address, "signature": signed.signature.hex()})
    return r2.json()["token"], acct.address.lower()


async def test_non_admin_forbidden(client):
    token, _ = await _login(client)
    r = await client.get("/api/admin/overview", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


async def test_no_auth_unauthorized(client):
    assert (await client.get("/api/admin/overview")).status_code == 401


async def test_admin_overview_and_flags(client):
    token, addr = await _login(client)
    get_settings().admin_identifiers = addr  # делаем этого юзера админом
    auth = {"Authorization": f"Bearer {token}"}

    ov = await client.get("/api/admin/overview", headers=auth)
    assert ov.status_code == 200
    assert "users" in ov.json() and ov.json()["users"] >= 1

    fl = await client.get("/api/admin/flags", headers=auth)
    assert fl.status_code == 200
    assert fl.json()["live_trading_enabled"] is False  # OFF по умолчанию


async def test_admin_set_tier(client):
    token, addr = await _login(client)
    get_settings().admin_identifiers = addr
    auth = {"Authorization": f"Bearer {token}"}

    users = (await client.get("/api/admin/users", headers=auth)).json()
    uid = users[0]["id"]

    r = await client.post(f"/api/admin/users/{uid}/tier", json={"tier": "pro", "days": 30}, headers=auth)
    assert r.status_code == 200

    me = await client.get("/api/auth/me", headers=auth)
    assert me.json()["tier"] == "pro"
