"""Контент-движок: оригинальные статьи, slug, дневная планка, API."""
from __future__ import annotations

import httpx
import pytest
import respx
from asgi_lifespan import LifespanManager
from httpx import ASGITransport
from sqlalchemy import func, select

from app.ai.content import fallback_article, slugify
from app.ai.runner import run_tick
from app.config import get_settings
from app.db import create_all, get_sessionmaker
from app.models import Article

from .conftest import FIXTURES


def _rss():
    return (FIXTURES / "rss_feed.xml").read_text(encoding="utf-8")


def test_slugify():
    assert slugify("TokenX gets listed on Binance!") == "tokenx-gets-listed-on-binance"
    assert slugify("Разблокировка $MIRA 10%")  # не падает на кириллице


def test_fallback_article_is_original_with_attribution():
    a = fallback_article("DeFi protocol suffers exploit", "exploit",
                         "news.example", "https://news.example/x", "en")
    assert a["model"] == "rules"
    assert len(a["title"]) <= 70
    assert len(a["meta_description"]) <= 155
    assert "news.example/x" in a["body"]            # атрибуция-ссылка
    assert "not financial advice" in a["body"].lower()
    assert "##" in a["body"]                        # структура для SEO


@respx.mock(assert_all_called=False)
async def test_articles_respect_daily_cap(respx_mock):
    s = get_settings()
    s.news_feeds = "https://news.example/rss"
    s.articles_per_day = 1               # планка = 1
    respx_mock.get("https://news.example/rss").mock(
        return_value=httpx.Response(200, text=_rss())
    )
    await create_all()
    _added, _cls, made = await run_tick(s)
    assert made == 1                     # не больше планки за день
    async with get_sessionmaker()() as sess:
        total = (await sess.execute(select(func.count()).select_from(Article))).scalar_one()
    assert total == 1
    # Второй тик в тот же день — планка исчерпана.
    _a, _c, made2 = await run_tick(s)
    assert made2 == 0


@pytest.fixture
async def client():
    from app.main import app

    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@respx.mock(assert_all_called=False)
async def test_articles_api(client, respx_mock):
    s = get_settings()
    s.news_feeds = "https://news.example/rss"
    s.articles_per_day = 5
    respx_mock.get("https://news.example/rss").mock(
        return_value=httpx.Response(200, text=_rss())
    )
    await run_tick(s)

    r = await client.get("/api/articles")
    body = r.json()
    assert body["total"] >= 1
    slug = body["items"][0]["slug"]
    assert body["items"][0]["meta_description"]

    r2 = await client.get(f"/api/articles/{slug}")
    assert r2.status_code == 200
    assert "body" in r2.json() and r2.json()["body"]
