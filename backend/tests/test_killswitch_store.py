"""Аварийная остановка в Redis — общее состояние для всех воркеров (ТЗ §6).

Состояние живёт в одном ключе Redis, чтобы discovery/paper/live видели одну остановку.
При срабатывании уходит системный алерт. Тесты герметичны (fakeredis + стаб-алертер).
"""
from __future__ import annotations

import pytest

from app.risk import killswitch_store as ks


class _CapturingAlerter:
    def __init__(self):
        self.calls: list[tuple[str, str, str]] = []

    async def alert(self, code, message, *, severity="error", dedup_seconds=3600, http=None):
        self.calls.append((code, message, severity))
        return True


async def test_default_inactive_when_empty(fake_redis):
    st = await ks.get_state(fake_redis)
    assert not st.active
    assert st.reason is None


async def test_inactive_when_no_redis():
    st = await ks.get_state(None)
    assert not st.active


async def test_trip_sets_state_and_persists(fake_redis):
    st = await ks.trip(fake_redis, "admin_manual")
    assert st.active and st.reason == "admin_manual" and st.tripped_at is not None
    # Другой «процесс» (повторное чтение) видит ту же остановку.
    again = await ks.get_state(fake_redis)
    assert again.active and again.reason == "admin_manual"


async def test_trip_sends_system_alert(fake_redis):
    alerter = _CapturingAlerter()
    await ks.trip(fake_redis, "balance_mismatch", alerter=alerter)
    assert alerter.calls, "ожидался системный алерт при срабатывании"
    code, _msg, severity = alerter.calls[0]
    assert code == "emergency_stop"
    assert severity == "critical"


async def test_clear_resets(fake_redis):
    await ks.trip(fake_redis, "admin_manual")
    cleared = await ks.clear(fake_redis)
    assert not cleared.active
    assert not (await ks.get_state(fake_redis)).active


async def test_unknown_reason_rejected(fake_redis):
    with pytest.raises(ValueError):
        await ks.trip(fake_redis, "not_a_reason")


async def test_bytes_payload_decoded(fake_redis):
    # Redis без decode_responses вернул бы bytes — get_state не должен падать.
    import json
    await fake_redis.set(ks.KEY, json.dumps({"active": True, "reason": "limit_breach"}).encode())
    st = await ks.get_state(fake_redis)
    assert st.active and st.reason == "limit_breach"
