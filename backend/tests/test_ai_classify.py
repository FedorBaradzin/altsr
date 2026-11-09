"""Классификация новостей: фолбэк по правилам + LLM-путь (respx)."""
from __future__ import annotations

import httpx
import respx

from app.ai.classify import classify, fallback_classify
from app.config import get_settings
from app.discovery.base import HttpClient


def test_fallback_listing_positive():
    r = fallback_classify("TokenX listed on Binance", "listing soon")
    assert r["catalyst"] == "listing"
    assert r["sentiment"] > 0
    assert r["urgency"] == "med"
    assert r["model"] == "rules"


def test_fallback_exploit_negative_high_urgency():
    r = fallback_classify("Protocol exploit drains funds", None)
    assert r["catalyst"] == "exploit"
    assert r["sentiment"] < 0
    assert r["urgency"] == "high"


def test_fallback_russian_keywords():
    r = fallback_classify("Крупная разблокировка токенов на этой неделе", None)
    assert r["catalyst"] == "unlock"


def test_fallback_other_neutral():
    r = fallback_classify("Weekly market recap", "nothing special")
    assert r["catalyst"] == "other"
    assert r["sentiment"] == 0.0
    assert r["urgency"] == "low"


async def test_classify_uses_fallback_without_key():
    s = get_settings()  # ai_enabled=False по умолчанию
    async with HttpClient() as http:
        r = await classify("Audit by CertiK completed", None, s, http)
    assert r["catalyst"] == "audit"
    assert r["model"] == "rules"


@respx.mock(assert_all_called=True)
async def test_classify_llm_path(respx_mock):
    s = get_settings()
    s.ai_enabled = True
    s.ai_api_key = "k"
    payload = {"choices": [{"message": {"content":
        '{"catalyst":"partnership","sentiment":0.8,"urgency":"med","credibility":"OFFICIALLY ANNOUNCED"}'}}]}
    respx_mock.post(f"{s.ai_base_url}/chat/completions").mock(
        return_value=httpx.Response(200, json=payload)
    )
    async with HttpClient() as http:
        r = await classify("X partners with Y", None, s, http)
    assert r["catalyst"] == "partnership"
    assert r["sentiment"] == 0.8
    assert r["model"] == s.ai_model


@respx.mock(assert_all_called=True)
async def test_classify_llm_failure_falls_back(respx_mock):
    s = get_settings()
    s.ai_enabled = True
    s.ai_api_key = "k"
    respx_mock.post(f"{s.ai_base_url}/chat/completions").mock(
        return_value=httpx.Response(500)
    )
    async with HttpClient() as http:
        r = await classify("Token listed on Coinbase", None, s, http)
    assert r["model"] == "rules"  # откат на правила
    assert r["catalyst"] == "listing"
