"""Публичная read-only статистика бумажного счёта владельца — для лендинга.

Без авторизации. Отдаёт только агрегаты (equity / доходность / win-rate /
число позиций / реализованный P&L) по счёту первого ADMIN_IDENTIFIERS —
никаких адресов, символов или чужих данных. Нужно, чтобы на главной
показывать РЕАЛЬНЫЙ бумажный счёт автоторговли, а не демо-формулу.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_session
from ..models import User, UserPaperAccount
from .user_paper import _assemble

router = APIRouter(prefix="/api/public", tags=["public"])


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
                "liquidity_usd": round(liq, 0),
                "age_hours": age_hours,
                "risk_score": report.risk_score,
                "verdict": "PASS",
                "low_liquidity": liq < settings.radar_low_liquidity_usd,
                "trending": trending,
                "change_24h": ch24,
                "multiple": multiple,
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
