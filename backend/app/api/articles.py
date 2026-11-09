"""REST-эндпоинты SEO-статей (блог)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Article
from ..schemas import ArticleCard, ArticleList, ArticleOut

router = APIRouter(prefix="/api", tags=["articles"])


@router.get("/articles", response_model=ArticleList)
async def list_articles(
    session: AsyncSession = Depends(get_session),
    lang: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ArticleList:
    where = [Article.status == "published"]
    if lang:
        where.append(Article.lang == lang)
    total = (
        await session.execute(select(func.count()).select_from(Article).where(*where))
    ).scalar_one()
    rows = (
        await session.execute(
            select(Article).where(*where)
            .order_by(Article.published_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()
    return ArticleList(items=[ArticleCard.model_validate(a) for a in rows], total=total)


@router.get("/articles/{slug}", response_model=ArticleOut)
async def get_article(slug: str, session: AsyncSession = Depends(get_session)) -> ArticleOut:
    art = (
        await session.execute(select(Article).where(Article.slug == slug))
    ).scalar_one_or_none()
    if art is None:
        raise HTTPException(status_code=404, detail="Статья не найдена")
    return ArticleOut.model_validate(art)
