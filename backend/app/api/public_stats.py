"""Публичная read-only статистика бумажного счёта владельца — для лендинга.

Без авторизации. Отдаёт только агрегаты (equity / доходность / win-rate /
число позиций / реализованный P&L) по счёту первого ADMIN_IDENTIFIERS —
никаких адресов, символов или чужих данных. Нужно, чтобы на главной
показывать РЕАЛЬНЫЙ бумажный счёт автоторговли, а не демо-формулу.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_session
from ..discovery import geckoterminal as gt
from ..discovery.base import HttpClient
from ..models import User, UserPaperAccount
from .user_paper import _assemble

router = APIRouter(prefix="/api/public", tags=["public"])

# --- OHLCV-кэш для графиков (item 1). ---
# GeckoTerminal keyless ~5 req/min, а график на лендинге дёргают много посетителей,
# поэтому кэшируем по (network,pool,timeframe,limit) на короткий TTL. Кэш — на процесс
# (у бэкенда может быть несколько воркеров), этого достаточно: данные свечей обновляются
# не чаще раза в ~30-60с, а лимит провайдера бережём жёстко.
_OHLCV_CACHE: dict[str, tuple[float, dict]] = {}
_OHLCV_TTL = 60.0

# Категории меняются медленно — кэшируем дольше (item 5).
_CATEGORIES_CACHE: dict[str, tuple[float, dict]] = {}
_CATEGORIES_TTL = 300.0


async def _owner_account(session: AsyncSession) -> UserPaperAccount | None:
    """Счёт владельца: первый из ADMIN_IDENTIFIERS (email или subject), у кого
    реально открыт бумажный счёт. Идентификаторов может быть несколько, а счёт —
    только у одного из них, поэтому перебираем всех админов."""
    ids = get_settings().admin_identifier_list
    if not ids:
        return None
    users = (
        await session.execute(
            select(User).where(
                or_(
                    func.lower(User.email).in_(ids),
                    func.lower(User.subject).in_(ids),
                )
            )
        )
    ).scalars().all()
    for u in users:
        acc = (
            await session.execute(
                select(UserPaperAccount).where(UserPaperAccount.user_id == u.id)
            )
        ).scalar_one_or_none()
        if acc is not None:
            return acc
    return None


@router.get("/paper")
async def public_paper(session: AsyncSession = Depends(get_session)) -> dict:
    acc = await _owner_account(session)
    if acc is None:
        return {"opened": False}
    out = await _assemble(session, acc)
    realized = round(sum(t.pnl_usd for t in out.trades), 2)
    wins = sum(1 for t in out.trades if t.pnl_usd >= 0)
    return {
        "opened": True,
        "start": round(out.start_balance),
        "equity": round(out.equity),
        "cash": round(out.cash),
        "return_pct": out.pnl_pct,
        "win_rate": out.win_rate,
        "open_positions": len(out.positions),
        "closed": len(out.trades),
        "wins": wins,
        "losses": len(out.trades) - wins,
        "realized_pnl": realized,
    }


@router.get("/radar")
async def public_radar(session: AsyncSession = Depends(get_session)) -> dict:
    """Публичная статистика работы радара для лендинга (реальные агрегаты).

    Честные счётчики: сколько монет отслежено, за 24ч, анти-скам проверок,
    пойманных скам-токенов и прошедших проверку (PASS). Без демо-формул.
    """
    from datetime import datetime, timedelta, timezone

    from ..models import SafetyReport, Signal, Token

    async def _count(stmt):
        return int((await session.execute(stmt)).scalar_one() or 0)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    tokens_total = await _count(select(func.count()).select_from(Token))
    tokens_24h = await _count(
        select(func.count()).select_from(Token).where(Token.discovered_at >= cutoff)
    )
    checks_total = await _count(select(func.count()).select_from(SafetyReport))
    scams_blocked = await _count(
        select(func.count()).select_from(SafetyReport).where(SafetyReport.verdict == "BLOCK")
    )
    clean_pass = await _count(
        select(func.count()).select_from(SafetyReport).where(SafetyReport.verdict == "PASS")
    )
    active_signals = await _count(select(func.count()).select_from(Signal))
    return {
        "tokens_total": tokens_total,
        "tokens_24h": tokens_24h,
        "checks_total": checks_total,
        "scams_blocked": scams_blocked,
        "clean_pass": clean_pass,
        "active_signals": active_signals,
    }


@router.get("/verified")
async def public_verified(
    limit: int = Query(default=30, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Публичная таблица "Проверенные / держатся" для лендинга.

    Токены, прошедшие анти-скам (verdict=PASS) и "выжившие" — т.е. с известным
    возрастом не меньше порога. Это честный список переживших выход, а не
    обещание прибыли. Сортировка по ликвидности. Без демо-данных.
    """
    from datetime import datetime, timedelta, timezone

    from ..models import SafetyReport, Token

    settings = get_settings()
    now = datetime.now(timezone.utc)
    age_cutoff = now - timedelta(hours=settings.verified_min_age_hours)

    # Санитарный потолок ликвидности: источники иногда отдают мусорные значения
    # (FDV/резерв как $1B+). Для честной витрины «проверенных» отсекаем абсурд.
    # Для трендовых токенов (source содержит "trending") потолок выше — это
    # качественные активно торгуемые монеты, которым позволяем до 50M.
    max_liq = settings.verified_max_liquidity_usd
    fetch_ceiling = max(max_liq, 50_000_000)
    # Берём с запасом — ниже дедуплицируем по символу/адресу и обрезаем до limit.
    rows = (
        await session.execute(
            select(Token, SafetyReport)
            .join(SafetyReport, SafetyReport.token_id == Token.id)
            .where(
                SafetyReport.verdict == "PASS",
                Token.liquidity_usd.is_not(None),
                Token.liquidity_usd > 0,
                Token.liquidity_usd <= fetch_ceiling,
                Token.created_at.is_not(None),
                Token.created_at <= age_cutoff,
            )
            .order_by(Token.liquidity_usd.desc())
            .limit(min(limit * 8, 400))
        )
    ).all()

    tokens: list[dict] = []
    seen: set[str] = set()
    for token, report in rows:
        # Дедуп: один токен на символ (или адрес, если символа нет) — убираем
        # повторы одного и того же проекта из разных пулов/источников.
        key = (token.symbol or token.address or "").strip().lower()
        if key in seen:
            continue
        liq = float(token.liquidity_usd)
        trending = "trending" in ((token.source or "").lower())
        # Не-трендовый мусор капаем на обычном потолке; трендовые качественные
        # токены пропускаем до 50M.
        if not trending and liq > max_liq:
            continue
        seen.add(key)
        created = token.created_at
        # created_at может прийти naive (без tz) из БД — приводим к UTC, чтобы
        # вычитание не падало.
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_hours = round((now - created).total_seconds() / 3600.0, 1)
        # Изменение цены за 24ч (%) — реальные ончейн-данные, не выдуманный профит.
        ch24 = token.price_change_h24
        ch24 = round(float(ch24), 1) if ch24 is not None else None
        # «Иксы» с момента обнаружения = текущая / базовая цена. Показываем только
        # при валидной базе; иначе None (на фронте скрываем).
        multiple = None
        if (
            token.price_usd is not None
            and token.first_price_usd is not None
            and token.first_price_usd > 0
        ):
            multiple = round(float(token.price_usd) / float(token.first_price_usd), 2)
        tokens.append(
            {
                "symbol": token.symbol,
                "chain": token.chain,
                "address": token.address,
                "pair_address": token.pair_address,
                "liquidity_usd": round(liq, 0),
                "age_hours": age_hours,
                "risk_score": report.risk_score,
                "verdict": "PASS",
                "low_liquidity": liq < settings.radar_low_liquidity_usd,
                "trending": trending,
                "change_24h": ch24,
                "multiple": multiple,
                "smart_wallets": token.smart_wallets or 0,
            }
        )

    # Приоритет: сначала трендовые, затем по ликвидности убыв. Обрезаем до limit.
    tokens.sort(key=lambda t: (not t["trending"], -t["liquidity_usd"]))
    tokens = tokens[:limit]

    return {
        "low_liq_threshold": settings.radar_low_liquidity_usd,
        "count": len(tokens),
        "tokens": tokens,
    }


@router.get("/fresh")
async def public_fresh(
    limit: int = Query(default=12, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Растущие находки радара: PASS-токены с реальным ростом за 24ч.

    Показываем ×N за 24ч = (1 + price_change_h24/100). Это РЕАЛЬНОЕ движение
    цены самого токена из ончейн-данных (GeckoTerminal), а не прибыль
    пользователя и не обещание доходности. Сортировка по росту убыв.
    """
    from datetime import datetime, timezone

    from ..models import SafetyReport, Token

    settings = get_settings()
    now = datetime.now(timezone.utc)
    fetch_ceiling = max(settings.verified_max_liquidity_usd, 50_000_000)

    rows = (
        await session.execute(
            select(Token, SafetyReport)
            .join(SafetyReport, SafetyReport.token_id == Token.id)
            .where(
                SafetyReport.verdict == "PASS",
                Token.price_change_h24.is_not(None),
                Token.price_change_h24 > 0,
                # Отсекаем абсурдные значения источника (микрокап-артефакты у цены
                # около нуля). Оставляем правдоподобные иксы — для доверия блока.
                Token.price_change_h24 <= settings.fresh_max_change_pct,
                Token.liquidity_usd.is_not(None),
                Token.liquidity_usd > 0,
                Token.liquidity_usd <= fetch_ceiling,
                Token.created_at.is_not(None),
            )
            .order_by(Token.price_change_h24.desc())
            .limit(min(limit * 6, 300))
        )
    ).all()

    tokens: list[dict] = []
    seen: set[str] = set()
    for token, report in rows:
        key = (token.symbol or token.address or "").strip().lower()
        if key in seen:
            continue
        seen.add(key)
        created = token.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_hours = round((now - created).total_seconds() / 3600.0, 1)
        ch24 = round(float(token.price_change_h24), 1)
        tokens.append(
            {
                "symbol": token.symbol,
                "chain": token.chain,
                "address": token.address,
                "pair_address": token.pair_address,
                "liquidity_usd": round(float(token.liquidity_usd), 0),
                "age_hours": age_hours,
                "risk_score": report.risk_score,
                "verdict": "PASS",
                "change_24h": ch24,
                "multiple_24h": round(1.0 + ch24 / 100.0, 2),
                "smart_wallets": token.smart_wallets or 0,
            }
        )
        if len(tokens) >= limit:
            break

    return {"count": len(tokens), "tokens": tokens}


@router.get("/ohlcv")
async def public_ohlcv(
    chain: str | None = Query(default=None, description="сеть токена (bsc/base/eth/solana)"),
    pool: str | None = Query(default=None, description="адрес пула (pair_address)"),
    token_id: int | None = Query(default=None, description="или id токена из /tokens"),
    timeframe: str = Query(default="hour", description="day|hour|minute"),
    aggregate: int = Query(default=1, ge=1, le=60),
    limit: int = Query(default=100, ge=1, le=300),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Реальные OHLCV-свечи пула из GeckoTerminal — для свечных графиков (item 1).

    Можно передать (chain + pool) напрямую ИЛИ token_id (тогда chain/pool берём из БД).
    Публичный, graceful: при любой проблеме → {"count": 0, "candles": []}, без 5xx.
    Это РЕАЛЬНЫЕ ончейн-данные цены, не прибыль пользователя и не обещание доходности.
    """
    empty = {"count": 0, "timeframe": timeframe, "candles": []}
    if timeframe not in gt.OHLCV_TIMEFRAMES:
        return {**empty, "error": "bad_timeframe"}

    # Резолв chain/pool по token_id, если переданы не напрямую.
    if token_id is not None and (not chain or not pool):
        from ..models import Token

        tok = (
            await session.execute(select(Token).where(Token.id == token_id))
        ).scalar_one_or_none()
        if tok is not None:
            chain = chain or tok.chain
            pool = pool or tok.pair_address

    network = gt.chain_to_network(chain)
    if not network or not pool:
        return empty

    key = f"{network}:{pool}:{timeframe}:{aggregate}:{limit}"
    now = time.monotonic()
    hit = _OHLCV_CACHE.get(key)
    if hit is not None and hit[0] > now:
        return hit[1]

    settings = get_settings()
    candles: list[gt.Candle] = []
    try:
        async with HttpClient(timeout=settings.http_timeout_seconds, max_retries=2) as http:
            candles = await gt.fetch_ohlcv(
                http, settings.gecko_base_url, network, pool,
                timeframe=timeframe, aggregate=aggregate, limit=limit,
            )
    except Exception:  # noqa: BLE001 — график не должен ронять ответ
        candles = []

    out = {
        "count": len(candles),
        "timeframe": timeframe,
        "network": network,
        "pool": pool,
        # Компактный формат свечей: [t, o, h, l, c, v] — t в unix-секундах.
        "candles": [[c.ts, c.open, c.high, c.low, c.close, c.volume] for c in candles],
    }
    # Кэшируем только непустой результат (пустой мог быть из-за моргнувшего лимита).
    if candles:
        _OHLCV_CACHE[key] = (now + _OHLCV_TTL, out)
    return out


@router.get("/categories")
async def public_categories(
    limit: int = Query(default=20, ge=1, le=50),
) -> dict:
    """Он-чейн категории/нарративы из GeckoTerminal (item 5) — что сейчас качает.

    Публичный, graceful: при недоступности keyless-эндпоинта → {"count": 0,
    "categories": []}. Кэш на 5 минут (категории меняются медленно).
    """
    key = f"cat:{limit}"
    now = time.monotonic()
    hit = _CATEGORIES_CACHE.get(key)
    if hit is not None and hit[0] > now:
        return hit[1]

    settings = get_settings()
    cats: list[dict] = []
    try:
        async with HttpClient(timeout=settings.http_timeout_seconds, max_retries=2) as http:
            cats = await gt.fetch_categories(http, settings.gecko_base_url, limit=limit)
    except Exception:  # noqa: BLE001
        cats = []

    out = {"count": len(cats), "categories": cats}
    if cats:
        _CATEGORIES_CACHE[key] = (now + _CATEGORIES_TTL, out)
    return out
