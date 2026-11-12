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
from ..discovery.base import HttpClient
from ..models import SafetyReport, Signal, Token
from ..notify.format import format_buy_alert
from ..notify.telegram import TelegramNotifier
from ..paper.executor import config_from_settings
from ..paper.exits import build_plan
from ..safety.screener import screen_token, store_result
from .engine import SignalInput, evaluate_entry
from .hard_rules import HardRuleInput
from .momentum import fetch_momentum
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
    settings: Settings,
    redis=None,
    notifier: TelegramNotifier | None = None,
    *,
    screen_fn=screen_token,
) -> int:
    notifier = notifier or TelegramNotifier(settings)
    now = datetime.now(timezone.utc)
    created = 0

    async with get_sessionmaker()() as session:
        rows = await _candidates(session, settings)
        if not rows:
            return 0

        # Один HttpClient на батч — для моментума (DexScreener) и свежей
        # перепроверки безопасности перед отправкой. Открываем, только если
        # что-то из этого включено; иначе работаем без сети.
        need_http = settings.momentum_enabled or settings.signal_recheck_safety_before_send
        if not need_http:
            created = await _emit_signals(
                settings, session, rows, {}, now, notifier, redis, None, screen_fn
            )
        else:
            async with HttpClient(
                timeout=settings.http_timeout_seconds, max_retries=settings.http_max_retries
            ) as http:
                moms: dict[int, object] = {}
                if settings.momentum_enabled:
                    for token, _rep in rows:
                        try:
                            m = await fetch_momentum(
                                http, settings.dexscreener_base_url, token.chain, token.address
                            )
                            if m is not None:
                                moms[token.id] = m
                        except Exception as exc:  # noqa: BLE001
                            logger.debug("моментум %s не получен: %s", token.address, exc)
                created = await _emit_signals(
                    settings, session, rows, moms, now, notifier, redis, http, screen_fn
                )

        await session.commit()
    return created


async def _recheck_blocks(
    settings: Settings, session: AsyncSession, http, token: Token, screen_fn
) -> tuple[bool, int | None]:
    """Свежая перепроверка безопасности ПЕРЕД отправкой в Telegram.

    Возвращает (blocked, fresh_risk_score). Хранимый safety-отчёт может устареть
    (токен получил PASS рано, позже помечен скамом) — перескриниваем кандидата,
    уже прошедшего ворота входа. Не PASS или malicious → блокируем сигнал и
    обновляем отчёт (лента/радар перестают показывать токен зелёным).

    Падение скрининга → blocked=True (нет свежего подтверждения — не шлём).
    Если перепроверка выключена или нет http — не блокируем, risk берём из отчёта.
    """
    if not settings.signal_recheck_safety_before_send or http is None:
        return False, None
    try:
        fresh = await screen_fn(http, settings, token.chain, token.address)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "пере-скрининг %s:%s упал — сигнал пропущен: %s",
            token.chain, token.address, exc,
        )
        return True, None
    try:
        await store_result(session, token, fresh)
    except Exception as exc:  # noqa: BLE001
        logger.debug("store_result при пере-скрининге не удался: %s", exc)
    if fresh.verdict != "PASS" or fresh.is_malicious:
        logger.info(
            "БЛОК перед Telegram %s:%s — свежий вердикт %s%s",
            token.chain, token.address, fresh.verdict,
            " (malicious)" if fresh.is_malicious else "",
        )
        return True, fresh.risk_score
    return False, fresh.risk_score


async def _emit_signals(
    settings: Settings,
    session: AsyncSession,
    rows: list[tuple[Token, SafetyReport]],
    moms: dict[int, object],
    now: datetime,
    notifier: TelegramNotifier,
    redis,
    http,
    screen_fn,
) -> int:
    created = 0
    for token, report in rows:
        mom = moms.get(token.id)
        inp = SignalInput(
            chain=token.chain,
            address=token.address,
            liquidity_usd=token.liquidity_usd,
            age_minutes=_age_minutes(token, now),
            holder_count=None,
            verdict=report.verdict,
            risk_score=report.risk_score,
            price_change_m5=getattr(mom, "price_change_m5", None),
            price_change_h1=getattr(mom, "price_change_h1", None),
            vol_h1=getattr(mom, "vol_h1", None),
            vol_h6=getattr(mom, "vol_h6", None),
            buys_m5=getattr(mom, "buys_m5", None),
            sells_m5=getattr(mom, "sells_m5", None),
        )
        # Hard-rules (T4): объём (R1) и давление продаж (R3) из моментума.
        # R2 (верификация) и R4 (dev/bundles) не прокидываем — нет данных,
        # чтобы не блокировать Solana без основания.
        hr = HardRuleInput(
            volume_usd=getattr(mom, "vol_h1", None),
            buys_m5=getattr(mom, "buys_m5", None),
            sells_m5=getattr(mom, "sells_m5", None),
        ) if settings.hard_rules_enabled else None
        decision = evaluate_entry(inp, settings, hr=hr)
        if not decision.passed:
            logger.debug("skip %s:%s — %s", token.chain, token.address, decision.rejected)
            continue

        # Свежая перепроверка безопасности перед самой отправкой (анти-скам).
        blocked, fresh_risk = await _recheck_blocks(settings, session, http, token, screen_fn)
        if blocked:
            continue
        risk_score = fresh_risk if fresh_risk is not None else report.risk_score

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
            name=token.name, confidence=decision.confidence, risk_score=risk_score,
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
