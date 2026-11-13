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


# --- мок прайс-фида: opening теперь требует реальную цену, поэтому в тестах
#     подменяем DexScreener на детерминированную карту цен (по умолчанию $1.0). ---
import app.api.autotrade as _at_mod  # noqa: E402
import app.api.user_paper as _up_mod  # noqa: E402

_PRICES: dict[tuple[str, str], float] = {}


async def _fake_prices(keys):
    return {k: _PRICES.get((k[0].lower(), k[1].lower()), 1.0) for k in keys}


def _set_price(chain: str, symbol: str, price: float) -> None:
    _PRICES[(chain.lower(), f"0x{symbol}".lower())] = price


@pytest.fixture(autouse=True)
def mock_dex_prices(monkeypatch):
    _PRICES.clear()
    monkeypatch.setattr(_at_mod, "get_live_price_map", _fake_prices)
    monkeypatch.setattr(_up_mod, "get_live_price_map", _fake_prices)
    yield
    _PRICES.clear()


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


async def test_second_tick_still_opens_from_existing_pool(client):
    """Регресс: сигнал, не влезший в кап на 1-м тике, открывается на 2-м.

    Старый код брал окно «created_at > last_run_at», поэтому после первого тика
    last_run_at==now и окно пустело — бот навсегда переставал открывать позиции.
    Фикс: фиксированное окно назад + дедуп по символу.
    """
    uid = await _mk_user("at_pool", "autonomous")
    h = _auth(uid)
    await _mk_signal("PAA", "solana", 0.97)
    await _mk_signal("PBB", "solana", 0.95)

    # кап = одна позиция: 1-й тик откроет только один символ
    await client.put("/api/autotrade/config", headers=h,
                     json={"enabled": True, "min_confidence": 0.9, "chains": "solana",
                           "max_position_usd": 100, "daily_cap_usd": 100})
    run1 = (await client.post("/api/autotrade/run", headers=h)).json()
    assert run1["opened"] == 1

    # поднимаем кап и тикаем снова — второй символ (из того же пула) должен открыться
    await client.put("/api/autotrade/config", headers=h, json={"daily_cap_usd": 1000})
    run2 = (await client.post("/api/autotrade/run", headers=h)).json()
    assert run2["opened"] == 1
    assert run2["open_positions"] == 2


async def test_reset_clears_autotrade_day_counter(client):
    """Сброс бумажного счёта обнуляет day_spent автотрейда, иначе бот стоит под капом."""
    uid = await _mk_user("at_reset", "autonomous")
    h = _auth(uid)
    await _mk_signal("RAA", "solana", 0.97)
    await client.put("/api/autotrade/config", headers=h,
                     json={"enabled": True, "min_confidence": 0.9, "chains": "solana",
                           "max_position_usd": 100, "daily_cap_usd": 100})
    await client.post("/api/autotrade/run", headers=h)
    assert (await client.get("/api/autotrade/config", headers=h)).json()["day_spent_usd"] == 100

    await client.post("/api/paper/me/reset", headers=h)
    cfg = (await client.get("/api/autotrade/config", headers=h)).json()
    assert cfg["day_spent_usd"] == 0
    assert cfg["last_run_at"] is None


async def test_real_price_drives_pnl_and_tp(client):
    """P&L идёт от реальной цены: вход по $1.0, цена +60% → закрытие по TP с ~+60%."""
    uid = await _mk_user("at_px", "autonomous")
    h = _auth(uid)
    await _mk_signal("ZZZ", "base", 0.97)
    await client.put("/api/autotrade/config", headers=h,
                     json={"enabled": True, "min_confidence": 0.9, "chains": "base",
                           "max_position_usd": 100, "daily_cap_usd": 1000,
                           "tp_pct": 50, "stop_pct": 25})
    r1 = (await client.post("/api/autotrade/run", headers=h)).json()
    assert r1["opened"] == 1          # вход по реальной цене $1.0

    _set_price("base", "ZZZ", 1.6)    # цена выросла на 60%
    r2 = (await client.post("/api/autotrade/run", headers=h)).json()
    assert r2["closed"] == 1 and r2["opened"] == 0
    paper = (await client.get("/api/paper/me", headers=h)).json()
    assert len(paper["trades"]) == 1
    assert paper["trades"][0]["pnl_pct"] > 55   # реальные ~+60%, не формула


async def test_unpriced_signal_not_opened(client, monkeypatch):
    """Нет реальной цены — бот не открывает позицию (честно, не держим неоцениваемое)."""
    uid = await _mk_user("at_np", "autonomous")
    h = _auth(uid)
    await _mk_signal("NOP", "base", 0.97)

    async def _empty(keys):
        return {}
    monkeypatch.setattr(_at_mod, "get_live_price_map", _empty)

    await client.put("/api/autotrade/config", headers=h,
                     json={"enabled": True, "min_confidence": 0.9, "chains": "base"})
    r = (await client.post("/api/autotrade/run", headers=h)).json()
    assert r["opened"] == 0


async def test_disabled_is_noop(client):
    uid = await _mk_user("at_off", "autonomous")
    h = _auth(uid)
    run = (await client.post("/api/autotrade/run", headers=h)).json()
    assert run["enabled"] is False


async def test_background_tick_all_enabled(client):
    """Фоновый тикер прогоняет всех включённых пользователей без их токена."""
    from app.api.autotrade import tick_all_enabled

    uid = await _mk_user("at_bg", "autonomous")
    h = _auth(uid)
    await _mk_signal("BGX", "solana", 0.95)
    await client.put("/api/autotrade/config", headers=h,
                     json={"enabled": True, "min_confidence": 0.9, "chains": "solana"})
    processed = await tick_all_enabled()
    assert processed >= 1
    paper = (await client.get("/api/paper/me", headers=h)).json()
    assert paper["opened"] is True and len(paper["positions"]) >= 1
