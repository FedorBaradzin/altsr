"""Симуляционный автотрейд: гейт по тарифу, конфиг, и тик открывает позиции по сигналам."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport

from app.auth.tokens import issue_token
from app.config import get_settings
from app.db import get_sessionmaker
from app.models import Signal, Token, User


@pytest.fixture
async def client():
    from app.main import app
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def _mk_user(subject: str, tier: str) -> int:
    async with get_sessionmaker()() as s:
        u = User(auth_method="google", subject=subject, email=f"{subject}@x.com", tier=tier)
        s.add(u); await s.commit(); await s.refresh(u)
        return u.id


def _auth(uid: int) -> dict:
    return {"Authorization": "Bearer " + issue_token(uid, get_settings().jwt_secret, 24)}


async def _mk_signal(symbol: str, chain: str, conf: float) -> None:
    async with get_sessionmaker()() as s:
        t = Token(chain=chain, address=f"0x{symbol}", symbol=symbol, source="test")
        s.add(t); await s.commit(); await s.refresh(t)
        s.add(Signal(token_id=t.id, chain=chain, address=t.address, side="BUY", confidence=conf))
        await s.commit()


async def test_gate_autonomous_only(client):
    free = await _mk_user("at_free", "free")
    assert (await client.get("/api/autotrade/config", headers=_auth(free))).status_code == 402
    assert (await client.post("/api/autotrade/run", headers=_auth(free))).status_code == 402
    pro = await _mk_user("at_pro", "pro")
    assert (await client.get("/api/autotrade/config", headers=_auth(pro))).status_code == 402


async def test_config_defaults_and_update(client):
    uid = await _mk_user("at_cfg", "autonomous")
    h = _auth(uid)
    cfg = (await client.get("/api/autotrade/config", headers=h)).json()
    assert cfg["enabled"] is False and cfg["min_confidence"] == 0.9
    upd = (await client.put("/api/autotrade/config", headers=h,
           json={"enabled": True, "max_position_usd": 50, "min_confidence": 0.8, "chains": "solana"})).json()
    assert upd["enabled"] is True and upd["max_position_usd"] == 50 and upd["chains"] == "solana"


async def test_run_opens_positions_from_signals(client):
    uid = await _mk_user("at_run", "autonomous")
    h = _auth(uid)
    await _mk_signal("AAA", "solana", 0.97)
    await _mk_signal("BBB", "base", 0.95)
    await _mk_signal("CCC", "solana", 0.60)  # ниже порога → не берём

    # включаем, порог 0.9, только solana
    await client.put("/api/autotrade/config", headers=h,
                     json={"enabled": True, "min_confidence": 0.9, "chains": "solana", "max_position_usd": 100})
    run = (await client.post("/api/autotrade/run", headers=h)).json()
    assert run["enabled"] is True
    assert run["opened"] == 1          # только AAA (solana, conf 0.97); BBB не solana, CCC ниже порога
    assert run["open_positions"] == 1

    # бумажный счёт создан и позиция там
    paper = (await client.get("/api/paper/me", headers=h)).json()
    assert paper["opened"] is True
    assert any(p["symbol"] == "AAA" for p in paper["positions"])

    # повторный тик не дублирует ту же позицию
    run2 = (await client.post("/api/autotrade/run", headers=h)).json()
    assert run2["opened"] == 0


async def test_disabled_is_noop(client):
    uid = await _mk_user("at_off", "autonomous")
    h = _auth(uid)
    run = (await client.post("/api/autotrade/run", headers=h)).json()
    assert run["enabled"] is False
