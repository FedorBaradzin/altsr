"""Свежая перепроверка безопасности ПЕРЕД отправкой в Telegram (анти-скам).

Закрывает дыру: хранимый safety-отчёт устаревает (токен получил PASS рано, позже
помечен скамом), а воркер видел старый PASS и слал BUY. Теперь перед отправкой —
свежий перескрининг; не PASS / malicious → сигнал не создаётся и не уходит.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.config import get_settings
from app.db import create_all, get_sessionmaker
from app.discovery.base import NormalizedToken
from app.discovery.dedup import upsert_tokens
from app.models import SafetyReport, Signal
from app.safety.base import SafetyFindings
from app.safety.scoring import evaluate


class _RecordingNotifier:
    enabled = True

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str) -> None:
        self.sent.append(text)


async def _seed_stored_pass(address="0xstale", liquidity=8000.0, risk=10):
    """Токен с ХРАНИМЫМ вердиктом PASS (как будто отскринен рано)."""
    async with get_sessionmaker()() as s:
        res = await upsert_tokens(s, [
            NormalizedToken(chain="ethereum", address=address, source="t",
                            symbol="PEPE2", liquidity_usd=liquidity, pair_address="0xpair")
        ])
        token = res.inserted[0]
        s.add(SafetyReport(
            token_id=token.id, chain="ethereum", address=address,
            risk_score=risk, verdict="PASS", red_flags="[]", findings="{}",
            sources="goplus", created_at=datetime.now(timezone.utc),
        ))
        await s.commit()
        return token.id


def _clean_findings(address: str) -> SafetyFindings:
    return SafetyFindings(
        chain="ethereum", address=address,
        is_honeypot=False, sell_tax=0.0, buy_tax=0.0, mint_authority_active=False,
        top_holder_pct=0.1, lp_locked=True, holder_count=500, is_open_source=True,
    )


def _settings_recheck_on():
    s = get_settings()
    s.momentum_enabled = False       # без live-моментума
    s.signal_recheck_safety_before_send = True
    return s


async def test_fresh_scam_blocks_telegram_and_signal():
    """Свежий скрининг вернул malicious → ни сигнала, ни отправки; отчёт обновлён."""
    from app.signals.runner import run_batch

    await create_all()
    addr = "0xstale"
    await _seed_stored_pass(address=addr)

    async def fake_screen(http, settings, chain, address):
        f = _clean_findings(address)
        f.is_honeypot = True  # теперь это ханипот → BLOCK + is_malicious
        return evaluate(f)

    notifier = _RecordingNotifier()
    created = await run_batch(_settings_recheck_on(), notifier=notifier, screen_fn=fake_screen)

    assert created == 0
    assert notifier.sent == []  # в Telegram ничего не ушло
    async with get_sessionmaker()() as s:
        assert (await s.execute(select(Signal))).first() is None
        rep = (await s.execute(select(SafetyReport))).scalar_one()
        assert rep.verdict == "BLOCK"  # хранимый отчёт обновлён свежим вердиктом


async def test_fresh_pass_still_sends():
    """Свежий скрининг подтвердил PASS → сигнал создаётся и уходит."""
    from app.signals.runner import run_batch

    await create_all()
    addr = "0xgood"
    await _seed_stored_pass(address=addr, risk=25)

    async def fake_screen(http, settings, chain, address):
        return evaluate(_clean_findings(address))  # чистый → PASS, risk 0

    notifier = _RecordingNotifier()
    created = await run_batch(_settings_recheck_on(), notifier=notifier, screen_fn=fake_screen)

    assert created == 1
    assert len(notifier.sent) == 1
    async with get_sessionmaker()() as s:
        sig = (await s.execute(select(Signal))).scalar_one()
        assert sig.side == "BUY"


async def test_screen_failure_blocks_send():
    """Падение перескрининга → нет свежего подтверждения → сигнал не уходит."""
    from app.signals.runner import run_batch

    await create_all()
    await _seed_stored_pass(address="0xerr")

    async def fake_screen(http, settings, chain, address):
        raise RuntimeError("provider down")

    notifier = _RecordingNotifier()
    created = await run_batch(_settings_recheck_on(), notifier=notifier, screen_fn=fake_screen)

    assert created == 0
    assert notifier.sent == []


async def test_blocked_scam_sends_admin_alert(monkeypatch):
    """Пойманный перед отправкой скам → алерт в админский чат."""
    from app.signals import runner as runner_mod
    from app.signals.runner import run_batch

    await create_all()
    await _seed_stored_pass(address="0xscam")

    sent: list[tuple[str, str]] = []

    async def fake_send_to_chat(settings, chat_id, text, *, http=None):
        sent.append((chat_id, text))
        return True

    monkeypatch.setattr(runner_mod, "send_to_chat", fake_send_to_chat)

    async def fake_screen(http, settings, chain, address):
        f = _clean_findings(address)
        f.is_honeypot = True
        return evaluate(f)

    s = _settings_recheck_on()
    s.telegram_admin_chat_id = "999"
    s.signal_alert_on_blocked_scam = True

    created = await run_batch(s, notifier=_RecordingNotifier(), screen_fn=fake_screen)

    assert created == 0
    assert len(sent) == 1
    chat_id, text = sent[0]
    assert chat_id == "999"
    assert "перед отправкой" in text


async def test_no_admin_chat_no_alert(monkeypatch):
    """Админский чат не задан → алерт не шлётся (только блок + лог)."""
    from app.signals import runner as runner_mod
    from app.signals.runner import run_batch

    await create_all()
    await _seed_stored_pass(address="0xscam2")

    sent: list = []

    async def fake_send_to_chat(settings, chat_id, text, *, http=None):
        sent.append(chat_id)
        return True

    monkeypatch.setattr(runner_mod, "send_to_chat", fake_send_to_chat)

    async def fake_screen(http, settings, chain, address):
        f = _clean_findings(address)
        f.is_honeypot = True
        return evaluate(f)

    s = _settings_recheck_on()
    s.telegram_admin_chat_id = ""  # не настроен

    created = await run_batch(s, notifier=_RecordingNotifier(), screen_fn=fake_screen)

    assert created == 0
    assert sent == []


async def test_recheck_disabled_uses_stored_verdict():
    """Флаг выключен → старое поведение: шлём по хранимому PASS без сети."""
    from app.signals.runner import run_batch

    await create_all()
    await _seed_stored_pass(address="0xold")

    s = get_settings()
    s.momentum_enabled = False
    s.signal_recheck_safety_before_send = False

    called = {"n": 0}

    async def fake_screen(http, settings, chain, address):  # не должен вызываться
        called["n"] += 1
        return evaluate(_clean_findings(address))

    notifier = _RecordingNotifier()
    created = await run_batch(s, notifier=notifier, screen_fn=fake_screen)

    assert created == 1
    assert called["n"] == 0
    assert len(notifier.sent) == 1
