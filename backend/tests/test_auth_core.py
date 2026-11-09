"""Сессионные токены, Telegram-подпись, подпись кошелька, гейтинг тарифов."""
from __future__ import annotations

import hashlib
import hmac
import time

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import HTTPException

from app.auth.service import TIER_RANK, effective_tier, require_tier
from app.auth.telegram import verify_telegram_login
from app.auth.tokens import issue_token, verify_token
from app.auth.wallet import build_message, verify_eth_signature
from app.models import User


def test_token_roundtrip_and_tamper():
    t = issue_token(42, "secret", 1)
    assert verify_token(t, "secret") == 42
    assert verify_token(t, "other-secret") is None
    assert verify_token(t + "x", "secret") is None


def test_token_expiry():
    t = issue_token(1, "secret", ttl_hours=0)  # exp = now
    time.sleep(1.1)
    assert verify_token(t, "secret") is None


def _tg_data(token: str, **over):
    data = {"id": 777, "first_name": "Ann", "username": "ann", "auth_date": int(time.time())}
    data.update(over)
    pairs = "\n".join(f"{k}={data[k]}" for k in sorted(data))
    secret = hashlib.sha256(token.encode()).digest()
    data["hash"] = hmac.new(secret, pairs.encode(), hashlib.sha256).hexdigest()
    return data


def test_telegram_valid_and_invalid():
    assert verify_telegram_login(_tg_data("BOT"), "BOT") is True
    assert verify_telegram_login(_tg_data("BOT"), "OTHER") is False
    bad = _tg_data("BOT"); bad["hash"] = "deadbeef"
    assert verify_telegram_login(bad, "BOT") is False


def test_telegram_stale_rejected():
    assert verify_telegram_login(_tg_data("BOT", auth_date=1), "BOT") is False


def test_wallet_signature():
    acct = Account.create()
    msg = build_message("abc123")
    signed = Account.sign_message(encode_defunct(text=msg), acct.key)
    assert verify_eth_signature(acct.address, msg, signed.signature.hex()) is True
    assert verify_eth_signature(acct.address, msg + "x", signed.signature.hex()) is False


def test_tier_rank_and_effective():
    free = User(auth_method="wallet", subject="a", tier="free")
    assert effective_tier(free) == "free"
    from datetime import datetime, timedelta, timezone
    expired = User(auth_method="wallet", subject="b", tier="pro",
                   tier_expires_at=datetime.now(timezone.utc) - timedelta(days=1))
    assert effective_tier(expired) == "free"
    active = User(auth_method="wallet", subject="c", tier="pro",
                  tier_expires_at=datetime.now(timezone.utc) + timedelta(days=1))
    assert effective_tier(active) == "pro"
    assert TIER_RANK["trader"] > TIER_RANK["pro"] > TIER_RANK["free"]


async def test_require_tier_gating():
    from datetime import datetime, timedelta, timezone
    dep = require_tier("pro")
    free = User(auth_method="wallet", subject="a", tier="free")
    with pytest.raises(HTTPException) as ei:
        await dep(user=free)
    assert ei.value.status_code == 402
    pro = User(auth_method="wallet", subject="b", tier="pro",
               tier_expires_at=datetime.now(timezone.utc) + timedelta(days=5))
    assert await dep(user=pro) is pro
