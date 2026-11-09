"""REST-эндпоинт новостей с ИИ-классификацией."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import NewsItem
from ..schemas import NewsList, NewsOut

router = APIRouter(prefix="/api", tags=["news"])


@router.get("/news", response_model=NewsList)
async def list_news(
    session: AsyncSession = Depends(get_session),
    urgency: str | None = Query(default=None, description="low/med/high"),
    catalyst: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> NewsList:
    where = []
    if urgency:
        where.append(NewsItem.urgency == urgency)
    if catalyst:
        where.append(NewsItem.catalyst == catalyst)
    total = (
        await session.execute(select(func.count()).select_from(NewsItem).where(*where))
    ).scalar_one()
    rows = (
        await session.execute(
            select(NewsItem).where(*where)
            .order_by(NewsItem.created_at.desc()).limit(limit)
        )
    ).scalars().all()
    return NewsList(items=[NewsOut.model_validate(n) for n in rows], total=total)
