"""NOWPayments IPN-подпись + end-to-end: вход кошельком → checkout → IPN → апгрейд тарифа."""
from __future__ import annotations

import json

import httpx
import pytest
from asgi_lifespan import LifespanManager
from eth_account import Account
from eth_account.messages import encode_defunct
from httpx import ASGITransport

from app.billing.nowpayments import ipn_signature, verify_ipn
from app.config import get_settings


def test_ipn_signature_roundtrip():
    payload = {"order_id": "altsr-1", "payment_status": "finished", "price_amount": 29}
    sig = ipn_signature(payload, "secret")
    assert verify_ipn(payload, sig, "secret") is True
    assert verify_ipn(payload, sig, "other") is False
    assert verify_ipn(payload, "bad", "secret") is False
    assert verify_ipn(payload, sig, "") is False  # нет секрета → отказ


def test_ipn_signature_order_independent():
    a = {"b": 2, "a": 1}
    b = {"a": 1, "b": 2}
    assert ipn_signature(a, "s") == ipn_signature(b, "s")


@pytest.fixture
async def client():
    from app.main import app

    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def _login_wallet(client) -> tuple[str, str]:
    acct = Account.create()
    r = await client.post("/api/auth/wallet/nonce", json={"address": acct.address})
    msg = r.json()["message"]
    signed = Account.sign_message(encode_defunct(text=msg), acct.key)
    r2 = await client.post("/api/auth/wallet/verify",
                           json={"address": acct.address, "signature": signed.signature.hex()})
    assert r2.status_code == 200
    return r2.json()["token"], acct.address


async def test_tiers_endpoint(client):
    r = await client.get("/api/billing/tiers")
    ids = {t["id"] for t in r.json()}
    assert {"free", "pro", "trader", "team"} <= ids


async def test_full_wallet_login_checkout_ipn_upgrade(client):
    s = get_settings()
    s.nowpayments_ipn_secret = "ipnsecret"
    token, _addr = await _login_wallet(client)
    auth = {"Authorization": f"Bearer {token}"}

    # /api/me → free
    me = await client.get("/api/auth/me", headers=auth)
    assert me.json()["tier"] == "free"

    # checkout без авторизации → 401
    assert (await client.post("/api/billing/checkout", json={"tier": "pro"})).status_code == 401

    # checkout c авторизацией (ключа NOWPayments нет → invoice_url None, но payment создан)
    co = await client.post("/api/billing/checkout", json={"tier": "pro"}, headers=auth)
    assert co.status_code == 200
    pid = co.json()["payment_id"]

    # IPN с валидной подписью → апгрейд до pro
    payload = {"order_id": f"altsr-{pid}", "payment_status": "finished", "payment_id": "np1"}
    sig = ipn_signature(payload, "ipnsecret")
    ipn = await client.post("/api/billing/ipn", content=json.dumps(payload),
                            headers={"x-nowpayments-sig": sig, "content-type": "application/json"})
    assert ipn.status_code == 200

    me2 = await client.get("/api/auth/me", headers=auth)
    assert me2.json()["tier"] == "pro"
    assert me2.json()["tier_expires_at"] is not None


async def test_ipn_bad_signature_rejected(client):
    s = get_settings()
    s.nowpayments_ipn_secret = "ipnsecret"
    payload = {"order_id": "altsr-999", "payment_status": "finished"}
    r = await client.post("/api/billing/ipn", content=json.dumps(payload),
                          headers={"x-nowpayments-sig": "wrong", "content-type": "application/json"})
    assert r.status_code == 401
