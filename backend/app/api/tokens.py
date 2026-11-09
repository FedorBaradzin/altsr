"""REST-эндпоинты ленты токенов + отчётов безопасности."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import SafetyReport, Signal, Token
from ..schemas import SafetyOut, TokenList, TokenWithSafety

router = APIRouter(prefix="/api", tags=["tokens"])


@router.get("/tokens", response_model=TokenList)
async def list_tokens(
    session: AsyncSession = Depends(get_session),
    chain: str | None = Query(default=None, description="фильтр по сети"),
    verdict: str | None = Query(default=None, description="PASS/REVIEW/BLOCK"),
    min_liquidity: float | None = Query(default=None, ge=0),
    max_risk: int | None = Query(default=None, ge=0, le=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> TokenList:
    where = []
    if chain:
        where.append(Token.chain == chain.lower())
    if min_liquidity is not None:
        where.append(Token.liquidity_usd >= min_liquidity)
    if verdict:
        where.append(SafetyReport.verdict == verdict.upper())
    if max_risk is not None:
        where.append(SafetyReport.risk_score <= max_risk)

    base = (
        select(Token, SafetyReport, Signal)
        .outerjoin(SafetyReport, SafetyReport.token_id == Token.id)
        .outerjoin(Signal, Signal.token_id == Token.id)
        .where(*where)
    )

    total = (
        await session.execute(
            select(func.count()).select_from(base.subquery())
        )
    ).scalar_one()

    rows = (
        await session.execute(
            base.order_by(Token.discovered_at.desc()).limit(limit).offset(offset)
        )
    ).all()

    items: list[TokenWithSafety] = []
    for token, report, signal in rows:
        item = TokenWithSafety.model_validate(token)
        if report is not None:
            item.verdict = report.verdict
            item.risk_score = report.risk_score
        if signal is not None:
            item.signal_confidence = signal.confidence
        items.append(item)

    return TokenList(items=items, total=total, limit=limit, offset=offset)


@router.get("/tokens/{token_id}/safety", response_model=SafetyOut)
async def token_safety(
    token_id: int, session: AsyncSession = Depends(get_session)
) -> SafetyOut:
    report = (
        await session.execute(
            select(SafetyReport).where(SafetyReport.token_id == token_id)
        )
    ).scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail="Отчёт безопасности ещё не готов")
    return SafetyOut.from_report(report)
