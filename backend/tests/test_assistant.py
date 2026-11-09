"""Онлайн-консультант: FAQ-фолбэк, LLM-путь, эндпоинт."""
from __future__ import annotations

import httpx
import pytest
import respx
from asgi_lifespan import LifespanManager
from httpx import ASGITransport

from app.assistant.chat import answer
from app.assistant.faq import answer_from_faq
from app.config import get_settings
from app.discovery.base import HttpClient


def test_faq_matches():
    assert "Pro" in answer_from_faq("сколько стоит тариф?")
    assert "PASS" in answer_from_faq("как работает проверка на скам?")
    assert "не даю инвест" in answer_from_faq("что купить чтобы вырасло?").lower() or \
           "не даю" in answer_from_faq("какой токен купить?").lower()


def test_faq_generic_fallback():
    assert answer_from_faq("погода завтра")  # не падает, даёт общий ответ


async def test_answer_uses_faq_without_key():
    s = get_settings()
    async with HttpClient() as http:
        r = await answer([{"role": "user", "content": "что такое ALTSR?"}], s, http)
    assert "ALTSR" in r


@respx.mock(assert_all_called=True)
async def test_answer_llm_path(respx_mock):
    s = get_settings()
    s.ai_enabled = True
    s.ai_api_key = "k"
    respx_mock.post(f"{s.ai_base_url}/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": "Привет! Чем помочь?"}}]})
    )
    async with HttpClient() as http:
        r = await answer([{"role": "user", "content": "привет"}], s, http)
    assert r == "Привет! Чем помочь?"


@pytest.fixture
async def client():
    from app.main import app

    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def test_chat_endpoint(client):
    r = await client.post("/api/assistant/chat", json={"message": "какие тарифы?"})
    assert r.status_code == 200
    assert "answer" in r.json() and r.json()["answer"]
