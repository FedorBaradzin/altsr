"""REST-эндпоинты бумажной симуляции: сводка P&L, позиции, план."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_session
from ..models import PaperAccount, PaperPosition, SafetyReport, Signal
from ..paper.executor import config_from_settings
from ..paper.exits import build_plan
from ..reels.render import ReelData, render_reel_html
from ..schemas import PaperPositionList, PaperPositionOut, PaperSummaryOut

router = APIRouter(prefix="/api/paper", tags=["paper"])


@router.get("/summary", response_model=PaperSummaryOut)
async def paper_summary(session: AsyncSession = Depends(get_session)) -> PaperSummaryOut:
    settings = get_settings()
    acc = (
        await session.execute(select(PaperAccount).where(PaperAccount.id == 1))
    ).scalar_one_or_none()
    start = acc.start_balance if acc else settings.paper_start_balance
    cash = acc.cash if acc else settings.paper_start_balance
    realized = acc.realized_pnl if acc else 0.0

    positions = (await session.execute(select(PaperPosition))).scalars().all()
    unrealized = 0.0
    open_n = closed_n = wins = losses = 0
    win_pcts: list[float] = []
    loss_pcts: list[float] = []
    for p in positions:
        if p.status == "open":
            open_n += 1
            if p.entry_price:
                cur = p.size_usd * p.remaining_fraction * (p.last_price / p.entry_price)
                unrealized += cur - p.size_usd * p.remaining_fraction
        else:
            closed_n += 1
            if p.realized_pnl_usd >= 0:
                wins += 1
                if p.pnl_pct is not None:
                    win_pcts.append(p.pnl_pct)
            else:
                losses += 1
                if p.pnl_pct is not None:
                    loss_pcts.append(p.pnl_pct)

    equity = cash + unrealized + sum(
        p.size_usd * p.remaining_fraction for p in positions if p.status == "open"
    )
    return_pct = round((equity - start) / start * 100, 2) if start else 0.0

    return PaperSummaryOut(
        start_balance=round(start, 2), cash=round(cash, 2), equity=round(equity, 2),
        realized_pnl=round(realized, 2), unrealized_pnl=round(unrealized, 2),
        return_pct=return_pct, open_positions=open_n, closed_positions=closed_n,
        wins=wins, losses=losses,
        win_rate=round(wins / closed_n, 3) if closed_n else None,
        avg_win_pct=round(sum(win_pcts) / len(win_pcts), 2) if win_pcts else None,
        avg_loss_pct=round(sum(loss_pcts) / len(loss_pcts), 2) if loss_pcts else None,
        plan=build_plan(config_from_settings(settings)),
    )


@router.get("/positions", response_model=PaperPositionList)
async def paper_positions(
    session: AsyncSession = Depends(get_session),
    status: str | None = Query(default=None, description="open/closed"),
    limit: int = Query(default=100, ge=1, le=500),
) -> PaperPositionList:
    where = []
    if status:
        where.append(PaperPosition.status == status)
    total = (
        await session.execute(
            select(func.count()).select_from(PaperPosition).where(*where)
        )
    ).scalar_one()
    rows = (
        await session.execute(
            select(PaperPosition).where(*where)
            .order_by(PaperPosition.opened_at.desc()).limit(limit)
        )
    ).scalars().all()
    return PaperPositionList(
        items=[PaperPositionOut.from_position(p) for p in rows], total=total
    )


@router.get("/reels/top")
async def top_reels(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=12, ge=1, le=50),
    min_pnl_pct: float = Query(default=5.0, description="минимальная прибыль, %"),
) -> dict:
    """Лучшие прибыльные сделки — исходные данные для рилсов (выгодные сделки)."""
    rows = (
        await session.execute(
            select(PaperPosition)
            .where(
                PaperPosition.status == "closed",
                PaperPosition.pnl_pct.is_not(None),
                PaperPosition.pnl_pct >= min_pnl_pct,
            )
            .order_by(PaperPosition.pnl_pct.desc())
            .limit(limit)
        )
    ).scalars().all()
    items = [
        {
            "id": p.id,
            "symbol": p.symbol or p.address[:8],
            "chain": p.chain,
            "pnl_pct": round(p.pnl_pct or 0.0, 1),
            "pnl_usd": round(p.realized_pnl_usd, 0),
            "exit_reason": p.exit_reason,
            "closed_at": p.closed_at.isoformat() if p.closed_at else None,
            "reel_url": f"/api/paper/positions/{p.id}/reel",
        }
        for p in rows
    ]
    return {"items": items, "total": len(items)}


@router.get("/positions/{position_id}/reel", response_class=HTMLResponse)
async def position_reel(
    position_id: int,
    session: AsyncSession = Depends(get_session),
    lang: str = Query(default="ru"),
) -> HTMLResponse:
    """Рилс (вертикальный анимированный ролик) по позиции — как запись экрана платформы."""
    pos = (
        await session.execute(select(PaperPosition).where(PaperPosition.id == position_id))
    ).scalar_one_or_none()
    if pos is None:
        raise HTTPException(status_code=404, detail="Позиция не найдена")

    report = (
        await session.execute(
            select(SafetyReport).where(SafetyReport.token_id == pos.token_id)
        )
    ).scalar_one_or_none()
    signal = (
        await session.execute(select(Signal).where(Signal.token_id == pos.token_id))
    ).scalar_one_or_none()

    data = ReelData(
        symbol=pos.symbol or pos.address[:8],
        chain=pos.chain,
        verdict=report.verdict if report else "PASS",
        risk_score=report.risk_score if report else 0,
        status=pos.status,
        entry_price=pos.entry_price,
        last_price=pos.last_price,
        pnl_pct=pos.pnl_pct if pos.pnl_pct is not None else _unrealized_pct(pos),
        pnl_usd=pos.realized_pnl_usd if pos.status == "closed" else _unrealized_usd(pos),
        exit_reason=pos.exit_reason,
        confidence=signal.confidence if signal else None,
    )
    return HTMLResponse(content=render_reel_html(data, lang))


def _unrealized_pct(p: PaperPosition) -> float:
    if not p.entry_price:
        return 0.0
    return round((p.last_price / p.entry_price - 1) * 100, 2)


def _unrealized_usd(p: PaperPosition) -> float:
    if not p.entry_price:
        return 0.0
    return round(p.size_usd * p.remaining_fraction * (p.last_price / p.entry_price - 1), 2)
