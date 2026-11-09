"""Воркер сигналов: PASS-токены без сигнала → ворота входа → venues → БД → Telegram/шина."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..db import get_sessionmaker
from ..models import SafetyReport, Signal, Token
from ..notify.format import format_buy_alert
from ..notify.telegram import TelegramNotifier
from ..paper.executor import config_from_settings
from ..paper.exits import build_plan
from .engine import SignalInput, evaluate_entry
from .venues import build_buy_options

logger = logging.getLogger("altsr.signals.runner")

PUBSUB_CHANNEL = "altsr:signals"


def _age_minutes(token: Token, now: datetime) -> float | None:
    ref = token.created_at or token.discovered_at
    if ref is None:
        return None
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return max(0.0, (now - ref).total_seconds() / 60.0)


async def _candidates(session: AsyncSession, s: Settings) -> list[tuple[Token, SafetyReport]]:
    stmt = (
        select(Token, SafetyReport)
        .join(SafetyReport, SafetyReport.token_id == Token.id)
        .outerjoin(Signal, Signal.token_id == Token.id)
        .where(Signal.id.is_(None))
        .order_by(Token.discovered_at.desc())
        .limit(s.signal_batch_size)
    )
    if s.signal_require_pass:
        stmt = stmt.where(SafetyReport.verdict == "PASS")
    return list((await session.execute(stmt)).all())


async def run_batch(
    settings: Settings, redis=None, notifier: TelegramNotifier | None = None
) -> int:
    notifier = notifier or TelegramNotifier(settings)
    now = datetime.now(timezone.utc)
    created = 0

    async with get_sessionmaker()() as session:
        rows = await _candidates(session, settings)
        for token, report in rows:
            inp = SignalInput(
                chain=token.chain,
                address=token.address,
                liquidity_usd=token.liquidity_usd,
                age_minutes=_age_minutes(token, now),
                holder_count=None,
                verdict=report.verdict,
                risk_score=report.risk_score,
            )
            decision = evaluate_entry(inp, settings)
            if not decision.passed:
                logger.debug("skip %s:%s — %s", token.chain, token.address, decision.rejected)
                continue

            options = build_buy_options(token.chain, token.address, token.pair_address)
            signal = Signal(
                token_id=token.id,
                chain=token.chain,
                address=token.address,
                side="BUY",
                confidence=decision.confidence,
                reasons=json.dumps(decision.reasons, ensure_ascii=False),
                venues=json.dumps([o.as_dict() for o in options], ensure_ascii=False),
                status="new",
                created_at=now,
            )
            session.add(signal)
            await session.flush()
            created += 1

            # Уведомления.
            text = format_buy_alert(
                chain=token.chain, address=token.address, symbol=token.symbol,
                name=token.name, confidence=decision.confidence, risk_score=report.risk_score,
                reasons=decision.reasons, liquidity_usd=token.liquidity_usd, buy_options=options,
                plan=build_plan(config_from_settings(settings)),
            )
            await notifier.send(text)
            if redis is not None:
                try:
                    await redis.publish(PUBSUB_CHANNEL, json.dumps(
                        {"token_id": token.id, "chain": token.chain, "address": token.address,
                         "confidence": decision.confidence}, ensure_ascii=False))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("publish signal не удался: %s", exc)

        await session.commit()
    return created


async def run_forever(settings: Settings | None = None, redis=None) -> None:
    settings = settings or get_settings()
    notifier = TelegramNotifier(settings)
    logger.info("Signal-воркер стартовал: интервал %ds, Telegram=%s",
                settings.signal_interval_seconds, notifier.enabled)
    while True:
        try:
            n = await run_batch(settings, redis=redis, notifier=notifier)
            if n:
                logger.info("Создано сигналов: %d", n)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Ошибка в signal-тике: %s", exc)
        await asyncio.sleep(settings.signal_interval_seconds)
