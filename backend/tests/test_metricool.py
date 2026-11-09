"""Metricool: текст поста, планирование, интеграция в тик (под флагом)."""
from __future__ import annotations

import httpx
import respx
from sqlalchemy import select

from app.ai.runner import post_articles_to_social
from app.config import get_settings
from app.db import create_all, get_sessionmaker
from app.discovery.base import HttpClient
from app.models import Article
from app.social.metricool import build_post_text, schedule_post


def test_build_post_text():
    t = build_post_text("New token listed on Binance", "https://altsr.app/blog/x",
                        "listing crypto, new token")
    assert "https://altsr.app/blog/x" in t
    assert len(t) <= 240
    assert "#" in t


async def test_schedule_post_not_configured():
    s = get_settings()
    async with HttpClient() as http:
        assert await schedule_post(http, s, text="hi", when_iso="2026-01-01T00:00:00") is False


@respx.mock(assert_all_called=True)
async def test_schedule_post_ok(respx_mock):
    s = get_settings()
    s.metricool_user_token = "tok"
    s.metricool_user_id = "1"
    s.metricool_blog_id = "2"
    respx_mock.post(url__startswith=f"{s.metricool_base_url}/v2/scheduler/posts").mock(
        return_value=httpx.Response(200, json={"id": "p1"})
    )
    async with HttpClient() as http:
        ok = await schedule_post(http, s, text="hi", when_iso="2026-01-01T00:00:00")
    assert ok is True


async def test_post_articles_flag_off():
    s = get_settings()  # metricool_enabled=False
    await create_all()
    async with get_sessionmaker()() as sess:
        sess.add(Article(slug="a1", lang="en", title="T", meta_description="d",
                         body="b", status="published", social_posted=False))
        await sess.commit()
        assert await post_articles_to_social(sess, s, None) == 0  # http не нужен, выходит раньше


@respx.mock(assert_all_called=False)
async def test_post_articles_marks_posted(respx_mock):
    s = get_settings()
    s.metricool_enabled = True
    s.metricool_user_token = "tok"; s.metricool_user_id = "1"; s.metricool_blog_id = "2"
    respx_mock.post(url__startswith=f"{s.metricool_base_url}/v2/scheduler/posts").mock(
        return_value=httpx.Response(200, json={"id": "p1"})
    )
    await create_all()
    async with get_sessionmaker()() as sess:
        sess.add(Article(slug="a2", lang="en", title="T2", meta_description="d",
                         body="b", status="published", social_posted=False, keywords="crypto"))
        await sess.commit()
    async with HttpClient() as http:
        async with get_sessionmaker()() as sess:
            n = await post_articles_to_social(sess, s, http)
            await sess.commit()
    assert n == 1
    async with get_sessionmaker()() as sess:
        a = (await sess.execute(select(Article).where(Article.slug == "a2"))).scalar_one()
        assert a.social_posted is True
