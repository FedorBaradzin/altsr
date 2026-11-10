"""Аварийная остановка в Redis — общее состояние для всех воркеров (ТЗ §6).

Состояние хранится в одном ключе Redis, чтобы все процессы (discovery, paper, live,
backend) видели одну и ту же остановку. Пока остановка активна, новые входы запрещены
везде, где вызывается Risk Engine / гейты.

При срабатывании уходит системный алерт в Telegram (через SystemAlerter). Чистой логики
переходов касается killswitch.py; здесь — только персистентность в Redis и алерт.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from .killswitch import TRIP_REASONS, KillSwitchState

logger = logging.getLogger("altsr.risk.killswitch_store")

KEY = "altsr:killswitch"


def _decode(raw) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        return raw.decode("utf-8", "replace")
    return str(raw)


async def get_state(redis) -> KillSwitchState:
    """Прочитать состояние остановки. Недоступный Redis трактуем как «не активна»."""
    if redis is None:
        return KillSwitchState(active=False)
    try:
        raw = await redis.get(KEY)
    except Exception as exc:  # noqa: BLE001 — Redis не должен ронять гейт
        logger.warning("Kill-switch: Redis недоступен (%s) — считаем неактивным", exc)
        return KillSwitchState(active=False)
    text = _decode(raw)
    if not text:
        return KillSwitchState(active=False)
    try:
        d = json.loads(text)
    except (ValueError, TypeError):
        return KillSwitchState(active=False)
    ts = d.get("tripped_at")
    tripped_at = None
    if ts:
        try:
            tripped_at = datetime.fromisoformat(ts)
        except ValueError:
            tripped_at = None
    return KillSwitchState(active=bool(d.get("active")), reason=d.get("reason"),
                           tripped_at=tripped_at)


async def trip(redis, reason_code: str, *, alerter=None, now=None, http=None) -> KillSwitchState:
    """Активировать аварийную остановку: записать в Redis + системный алерт."""
    if reason_code not in TRIP_REASONS:
        raise ValueError(f"Неизвестная причина остановки: {reason_code!r}")
    now = now or datetime.now(timezone.utc)
    state = KillSwitchState(active=True, reason=reason_code, tripped_at=now)
    if redis is not None:
        try:
            await redis.set(KEY, json.dumps(
                {"active": True, "reason": reason_code, "tripped_at": now.isoformat()}))
        except Exception as exc:  # noqa: BLE001
            logger.error("Kill-switch: не удалось записать в Redis: %s", exc)
    logger.critical("KILL SWITCH АКТИВИРОВАН: %s — %s", reason_code, TRIP_REASONS[reason_code])
    if alerter is not None:
        await alerter.alert(
            "emergency_stop",
            f"🚨 Аварийная остановка: {TRIP_REASONS[reason_code]} ({reason_code}). "
            "Новые входы заблокированы.",
            severity="critical", dedup_seconds=0, http=http,
        )
    return state


async def clear(redis) -> KillSwitchState:
    """Снять остановку (только после проверки — ответственность вызывающего слоя)."""
    if redis is not None:
        try:
            await redis.delete(KEY)
        except Exception as exc:  # noqa: BLE001
            logger.error("Kill-switch: не удалось снять в Redis: %s", exc)
    logger.warning("Kill-switch снят")
    return KillSwitchState(active=False)
