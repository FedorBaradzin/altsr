"""RSS-парсинг + ингест/классификация/дедуп + API новостей."""
from __future__ import annotations

import httpx
import pytest
import respx
from asgi_lifespan import LifespanManager
from httpx import ASGITransport
from sqlalchemy import func, select

from app.ai.feeds import parse_feed
from app.ai.runner import run_tick
from app.config import get_settings
from app.db import create_all, get_sessionmaker
from app.models import NewsItem

from .conftest import FIXTURES


def _rss() -> str:
    return (FIXTURES / "rss_feed.xml").read_text(encoding="utf-8")


def test_parse_rss():
    items = parse_feed(_rss(), "news.example")
    assert len(items) == 2
    assert items[0].title.startswith("TokenX")
    assert items[0].url == "https://news.example/tokenx-binance"
    assert items[1].published_at is not None


@respx.mock(assert_all_called=False)
async def test_ingest_classify_and_dedup(respx_mock):
    s = get_settings()
    s.news_feeds = "https://news.example/rss"
    respx_mock.get("https://news.example/rss").mock(
        return_value=httpx.Response(200, text=_rss())
    )
    await create_all()

    added, classified, _articles = await run_tick(s)
    assert added == 2
    assert classified == 2

    async with get_sessionmaker()() as sess:
        rows = (await sess.execute(select(NewsItem))).scalars().all()
        cats = {r.catalyst for r in rows}
        assert "listing" in cats and "exploit" in cats
        assert all(r.classified for r in rows)
        # high-urgency эксплойт присутствует
        assert any(r.urgency == "high" for r in rows)

    # Повторный тик — дедуп по url, ничего нового.
    added2, _c, _a = await run_tick(s)
    assert added2 == 0
    async with get_sessionmaker()() as sess:
        total = (await sess.execute(select(func.count()).select_from(NewsItem))).scalar_one()
    assert total == 2


@pytest.fixture
async def client():
    from app.main import app

    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@respx.mock(assert_all_called=False)
async def test_news_api(client, respx_mock):
    s = get_settings()
    s.news_feeds = "https://news.example/rss"
    respx_mock.get("https://news.example/rss").mock(
        return_value=httpx.Response(200, text=_rss())
    )
    await run_tick(s)

    r = await client.get("/api/news")
    assert r.json()["total"] == 2

    r2 = await client.get("/api/news", params={"urgency": "high"})
    assert r2.json()["total"] == 1
    assert r2.json()["items"][0]["catalyst"] == "exploit"
