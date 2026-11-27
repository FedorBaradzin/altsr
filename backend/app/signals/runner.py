"""Воркер сигналов: PASS-токены без сигнала → ворота входа → venues → БД → Telegram/шина."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..db import get_sessionmaker
from ..discovery.base import HttpClient
from ..discovery.geckoterminal import chain_to_network, fetch_pool_trades, fetch_token_top_pool
from ..models import SafetyReport, Signal, Token
from ..notify.alerts import format_blocked_scam_alert
from ..notify.format import format_buy_alert
from ..notify.telegram import TelegramNotifier, send_to_chat
from ..paper.executor import config_from_settings
from ..paper.exits import build_plan
from ..safety.base import SafetyResult
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
    from datetime import timedelta
    from sqlalchemy import or_

    now = datetime.now(timezone.utc)
    stmt = (
        select(Token, SafetyReport)
        .join(SafetyReport, SafetyReport.token_id == Token.id)
        .outerjoin(Signal, Signal.token_id == Token.id)
        .where(Signal.id.is_(None))
    )
    # ПРЕД-ФИЛЬТР батча по жёстким гейтам (ликвидность/возраст/риск): иначе 30 слотов
    # забиваются заведомо непригодными (старые/мелкие/рисковые) новейшими токенами и
    # пригодные ранние кандидаты (в т.ч. Solana) не доходят до оценки. Живые гейты
    # (моментум, buy-pressure, объём) остаются в evaluate_entry.
    if s.signal_min_liquidity_usd > 0:
        stmt = stmt.where(
            Token.liquidity_usd.is_not(None),
            Token.liquidity_usd >= s.signal_min_liquidity_usd,
        )
    if s.signal_max_age_minutes > 0:
        cutoff = now - timedelta(minutes=s.signal_max_age_minutes)
        stmt = stmt.where(or_(Token.created_at.is_(None), Token.created_at >= cutoff))
    if s.signal_max_risk is not None:
        stmt = stmt.where(
            or_(SafetyReport.risk_score.is_(None), SafetyReport.risk_score <= s.signal_max_risk)
        )
    if s.autotrade_prefer_quality_sources:
        # Топ/трендовые источники — вперёд, иначе их топит поток свежих пулов и они не
        # попадают в batch (= не торгуются). Внутри группы — свежайшие первыми.
        from sqlalchemy import case

        src = func.lower(func.coalesce(Token.source, ""))
        priority = case(
            (src.like("%geckoterminal_top%"), 0),
            (src.like("%trending%"), 0),
            else_=1,
        )
        stmt = stmt.order_by(priority, Token.discovered_at.desc())
    else:
        stmt = stmt.order_by(Token.discovered_at.desc())
    stmt = stmt.limit(s.signal_batch_size)
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
        need_http = (
            settings.momentum_enabled
            or settings.signal_recheck_safety_before_send
            or settings.signal_gecko_trades_enabled
        )
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
) -> tuple[bool, SafetyResult | None]:
    """Свежая перепроверка безопасности ПЕРЕД отправкой в Telegram.

    Возвращает (blocked, fresh_result). Хранимый safety-отчёт может устареть
    (токен получил PASS рано, позже помечен скамом) — перескриниваем кандидата,
    уже прошедшего ворота входа. Не PASS или malicious → блокируем сигнал и
    обновляем отчёт (лента/радар перестают показывать токен зелёным).

    Падение скрининга → blocked=True, fresh=None (нет свежего подтверждения — не шлём).
    Если перепроверка выключена или нет http — не блокируем, fresh=None.
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
    # Блокируем ТОЛЬКО явный скам (BLOCK/malicious). REVIEW на ре-скрине — это, как
    # правило, пробел в данных источников (особенно Solana: RugCheck/GoPlus непостоянны),
    # а не скам; токен уже прошёл анти-скам при обнаружении (stored PASS). Раньше любой
    # не-PASS резал сигнал и это глушило Solana полностью.
    if fresh.verdict == "BLOCK" or fresh.is_malicious:
        logger.info(
            "БЛОК перед Telegram %s:%s — свежий вердикт %s%s",
            token.chain, token.address, fresh.verdict,
            " (malicious)" if fresh.is_malicious else "",
        )
        return True, fresh
    return False, fresh


async def _alert_blocked_scam(
    settings: Settings, token: Token, fresh: SafetyResult, http
) -> None:
    """Сообщить в админский чат, что перепроверка поймала скам перед отправкой."""
    if not settings.signal_alert_on_blocked_scam or not settings.telegram_admin_chat_id:
        return
    text = format_blocked_scam_alert(
        chain=token.chain, address=token.address, symbol=token.symbol,
        verdict=fresh.verdict,
        red_flag_codes=[f.code for f in fresh.red_flags if f.severity in ("hard", "soft")],
        malicious=fresh.is_malicious,
    )
    try:
        await send_to_chat(settings, settings.telegram_admin_chat_id, text, http=http)
    except Exception as exc:  # noqa: BLE001 — алерт не должен ронять тик
        logger.warning("админ-алерт о скаме не отправлен: %s", exc)


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
    trades_calls = 0  # лимит платных trades-вызовов за тик (защита квоты API)
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
            smart_wallets=getattr(token, "smart_wallets", None),
            # Качественный источник (trending ИЛИ top по объёму) проходит soft-гейт и
            # получает бонус к уверенности — это устоявшиеся ликвидные монеты, не свежак.
            is_trending=any(
                k in (token.source or "").lower() for k in ("trending", "top")
            ),
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

        # Ранний вход по РЕАЛЬНЫМ сделкам (Gecko trades, платный ключ). ЭКОНОМНО:
        # дёргаем trades ТОЛЬКО на кандидатах, уже прошедших дешёвые гейты (единицы
        # за тик) — перевес покупок (buy-pressure) + рост уникальных покупателей.
        if (
            settings.signal_gecko_trades_enabled and http is not None
            and trades_calls < settings.signal_gecko_trades_max_per_tick
        ):
            net = chain_to_network(token.chain)
            # Нужен адрес ПУЛА. Если pair_address пуст или равен адресу минта токена
            # (частый случай для Solana pump.fun) — резолвим самый ликвидный пул,
            # иначе эндпоинт trades отдаёт 404 и buy-pressure по Solana не считается.
            pool = token.pair_address
            if net and (not pool or pool == token.address):
                trades_calls += 1
                try:
                    pool = await fetch_token_top_pool(
                        http, settings.onchain_base_url, net, token.address,
                        headers=settings.onchain_headers,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("pool-resolve %s не удался: %s", token.address, exc)
                    pool = None
            agg = None
            if net and pool and trades_calls < settings.signal_gecko_trades_max_per_tick:
                trades_calls += 1
                try:
                    agg = await fetch_pool_trades(
                        http, settings.onchain_base_url, net, pool,
                        window_minutes=settings.signal_gecko_trades_window_min,
                        headers=settings.onchain_headers,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("trades %s не получены: %s", token.address, exc)
                    agg = None
            # buy_pressure=None при <5 сделок → ранний токен не блокируем.
            bp = agg.buy_pressure if agg is not None else None
            if bp is not None:
                if bp < settings.signal_min_buy_pressure:
                    logger.debug("skip %s — buy-pressure %.2f < %.2f",
                                 token.address, bp, settings.signal_min_buy_pressure)
                    continue
                if agg.buyers < settings.signal_min_trade_buyers:
                    logger.debug("skip %s — покупателей %d < %d",
                                 token.address, agg.buyers, settings.signal_min_trade_buyers)
                    continue
                decision.reasons.append(f"перевес покупок {bp:+.2f} ({agg.buyers} покуп.)")
                decision.confidence = min(
                    1.0,
                    decision.confidence + settings.signal_conf_w_trade_bp * min(1.0, bp),
                )

        # Растущая ликвидность → вклад в уверенность (без API, по first_liquidity_usd).
        if (
            settings.signal_conf_w_liq_growth > 0
            and token.first_liquidity_usd and token.liquidity_usd
            and token.liquidity_usd > token.first_liquidity_usd
        ):
            growth = (token.liquidity_usd - token.first_liquidity_usd) / token.first_liquidity_usd
            decision.reasons.append(f"ликвидность растёт +{growth*100:.0f}%")
            decision.confidence = min(
                1.0, decision.confidence + settings.signal_conf_w_liq_growth * min(1.0, growth)
            )

        # Свежая перепроверка безопасности перед самой отправкой (анти-скам).
        blocked, fresh = await _recheck_blocks(settings, session, http, token, screen_fn)
        if blocked:
            # Пойман скам до отправки — сообщаем в админский чат (если есть что).
            if fresh is not None:
                await _alert_blocked_scam(settings, token, fresh, http)
            continue
        risk_score = fresh.risk_score if fresh is not None else report.risk_score

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
