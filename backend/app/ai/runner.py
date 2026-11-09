"""ИИ-воркер: ингест новостей из фидов → дедуп → классификация → БД."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..db import get_sessionmaker
from ..discovery.base import HttpClient
from ..models import Article, NewsItem
from ..social.metricool import build_post_text, schedule_post
from .classify import classify
from .content import generate_article, slugify
from .feeds import fetch_feed

logger = logging.getLogger("altsr.ai.runner")


async def ingest_feeds(session: AsyncSession, s: Settings, http: HttpClient) -> int:
    added = 0
    for url in s.news_feed_list:
        source = url.split("//")[-1].split("/")[0]
        for item in await fetch_feed(http, url, source):
            exists = (
                await session.execute(select(NewsItem.id).where(NewsItem.url == item.url))
            ).scalar_one_or_none()
            if exists:
                continue
            session.add(NewsItem(
                source=item.source, url=item.url, title=item.title[:512],
                summary=item.summary, published_at=item.published_at, classified=False,
            ))
            added += 1
    await session.flush()
    return added


async def classify_batch(session: AsyncSession, s: Settings, http: HttpClient) -> int:
    rows = (
        await session.execute(
            select(NewsItem).where(NewsItem.classified.is_(False))
            .order_by(NewsItem.created_at.desc()).limit(s.news_batch_size)
        )
    ).scalars().all()
    done = 0
    for n in rows:
        result = await classify(n.title, n.summary, s, http, source=n.source)
        n.catalyst = result["catalyst"]
        n.sentiment = result["sentiment"]
        n.urgency = result["urgency"]
        n.credibility = result["credibility"]
        n.model = result["model"]
        n.classified = True
        done += 1
    await session.flush()
    return done


async def _unique_slug(session: AsyncSession, base: str) -> str:
    slug = base
    for n in range(1, 50):
        exists = (
            await session.execute(select(Article.id).where(Article.slug == slug))
        ).scalar_one_or_none()
        if not exists:
            return slug
        slug = f"{base}-{n}"
    return f"{base}-{int(datetime.now(timezone.utc).timestamp())}"


async def generate_articles(session: AsyncSession, s: Settings, http: HttpClient) -> int:
    """Собрать до дневной планки оригинальных SEO-статей из классифицированных новостей."""
    if not s.content_enabled:
        return 0
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today = (
        await session.execute(
            select(func.count()).select_from(Article).where(Article.published_at >= start)
        )
    ).scalar_one()
    remaining = s.articles_per_day - today
    if remaining <= 0:
        return 0

    # Новости, по которым ещё нет статьи; свежие и значимые — вперёд.
    stmt = (
        select(NewsItem)
        .outerjoin(Article, Article.news_id == NewsItem.id)
        .where(NewsItem.classified.is_(True), Article.id.is_(None))
        .order_by(NewsItem.created_at.desc())
        .limit(remaining)
    )
    rows = (await session.execute(stmt)).scalars().all()
    made = 0
    for n in rows:
        art = await generate_article(
            title=n.title, summary=n.summary, catalyst=n.catalyst,
            source_name=n.source, source_url=n.url, s=s, http=http,
        )
        slug = await _unique_slug(session, slugify(art["title"]))
        session.add(Article(
            slug=slug, lang=art["lang"], title=art["title"],
            meta_description=art["meta_description"], keywords=art["keywords"],
            body=art["body"], source_url=n.url, source_name=n.source, news_id=n.id,
            model=art["model"], status="published", published_at=datetime.now(timezone.utc),
        ))
        await session.flush()
        made += 1
    return made


async def post_articles_to_social(session: AsyncSession, s: Settings, http: HttpClient) -> int:
    """Поставить новые статьи в расписание Metricool (если включено)."""
    if not s.metricool_enabled:
        return 0
    from datetime import timedelta
    rows = (
        await session.execute(
            select(Article).where(
                Article.status == "published", Article.social_posted.is_(False)
            ).order_by(Article.published_at.desc()).limit(s.social_posts_per_run)
        )
    ).scalars().all()
    posted = 0
    when = (datetime.now(timezone.utc) + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S")
    for a in rows:
        link = f"{s.site_url.rstrip('/')}/blog/{a.slug}"
        text = build_post_text(a.title, link, a.keywords)
        if await schedule_post(http, s, text=text, when_iso=when):
            a.social_posted = True
            posted += 1
    await session.flush()
    return posted


async def run_tick(settings: Settings) -> tuple[int, int, int]:
    async with HttpClient(
        timeout=settings.http_timeout_seconds, max_retries=settings.http_max_retries
    ) as http:
        async with get_sessionmaker()() as session:
            added = await ingest_feeds(session, settings, http)
            classified = await classify_batch(session, settings, http)
            articles = await generate_articles(session, settings, http)
            try:
                await post_articles_to_social(session, settings, http)
            except Exception as exc:  # noqa: BLE001 — соц-постинг не критичен для тика
                logger.warning("Metricool-постинг не удался: %s", exc)
            await session.commit()
    return added, classified, articles


async def run_forever(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    logger.info("AI-воркер стартовал: фидов %d, LLM=%s",
                len(settings.news_feed_list), settings.ai_enabled and bool(settings.ai_api_key))
    while True:
        try:
            added, classified, articles = await run_tick(settings)
            if added or classified or articles:
                logger.info("Новости: +%d, классиф. %d, статей %d", added, classified, articles)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Ошибка в AI-тике: %s", exc)
        await asyncio.sleep(settings.news_interval_seconds)
