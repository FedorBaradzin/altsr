"""Классификация новости → структурированный выход.

Двухскоростная схема (см. roadmap): быстрый детерминированный фолбэк по правилам
работает всегда и без ключа; LLM-путь включается при AI_ENABLED + ключе и даёт более
тонкую оценку, но при любой ошибке мягко откатывается на правила.

Выход: catalyst, sentiment (−1..+1), urgency (low/med/high), credibility, model.
Это ОЦЕНКА, не факт и не прогноз цены.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from ..config import Settings
from ..discovery.base import HttpClient

logger = logging.getLogger("altsr.ai.classify")

CATALYSTS = ["listing", "partnership", "audit", "unlock", "exploit", "delisting", "other"]

# Ключевые слова (en + ru) → катализатор.
_KEYWORDS = {
    "listing": ["listing", "listed", "листинг", "листинге", "биржа", "binance", "coinbase"],
    "partnership": ["partnership", "partner", "integration", "партнёр", "партнерство", "интеграц"],
    "audit": ["audit", "audited", "аудит", "certik", "hacken"],
    "unlock": ["unlock", "vesting", "разблокировк", "анлок"],
    "exploit": ["exploit", "hack", "hacked", "drained", "rug", "взлом", "эксплойт", "слив"],
    "delisting": ["delist", "delisting", "delisted", "делистинг", "снят с торгов"],
}
_POSITIVE = {"listing", "partnership", "audit"}
_NEGATIVE = {"exploit", "delisting", "unlock"}
_HIGH_URGENCY = {"exploit", "delisting"}
_MED_URGENCY = {"listing", "unlock"}

_ALLOWED_CRED = {
    "VERIFIED", "OFFICIALLY ANNOUNCED", "THIRD-PARTY REPORTED",
    "ESTIMATED", "UNVERIFIED", "CONTRADICTED",
}


def fallback_classify(title: str, summary: str | None, source: str = "") -> dict[str, Any]:
    text = f"{title} {summary or ''}".lower()
    catalyst = "other"
    for cat, kws in _KEYWORDS.items():
        if any(k in text for k in kws):
            catalyst = cat
            break

    if catalyst in _POSITIVE:
        sentiment = 0.6
    elif catalyst in _NEGATIVE:
        sentiment = -0.6 if catalyst != "unlock" else -0.3
    else:
        sentiment = 0.0

    if catalyst in _HIGH_URGENCY:
        urgency = "high"
    elif catalyst in _MED_URGENCY:
        urgency = "med"
    else:
        urgency = "low"

    # Официальные источники считаем «официально заявлено».
    cred = "OFFICIALLY ANNOUNCED" if "official" in source.lower() else "THIRD-PARTY REPORTED"
    return {
        "catalyst": catalyst, "sentiment": sentiment, "urgency": urgency,
        "credibility": cred, "model": "rules",
    }


def _sanitize(d: dict[str, Any], source: str) -> dict[str, Any]:
    cat = d.get("catalyst")
    if cat not in CATALYSTS:
        cat = "other"
    try:
        sent = max(-1.0, min(1.0, float(d.get("sentiment", 0.0))))
    except (ValueError, TypeError):
        sent = 0.0
    urg = d.get("urgency")
    if urg not in ("low", "med", "high"):
        urg = "low"
    cred = d.get("credibility")
    if cred not in _ALLOWED_CRED:
        cred = "THIRD-PARTY REPORTED"
    return {"catalyst": cat, "sentiment": sent, "urgency": urg,
            "credibility": cred, "model": d.get("model", "llm")}


_SYS = (
    "Ты крипто-аналитик. Классифицируй новость строго как JSON без пояснений: "
    '{"catalyst": one of ' + str(CATALYSTS) + ', '
    '"sentiment": number -1..1, "urgency": "low"|"med"|"high", '
    '"credibility": "VERIFIED"|"OFFICIALLY ANNOUNCED"|"THIRD-PARTY REPORTED"|'
    '"ESTIMATED"|"UNVERIFIED"|"CONTRADICTED"}. '
    "Это оценка, не прогноз цены."
)


async def _llm_classify(
    title: str, summary: str | None, s: Settings, http: HttpClient
) -> dict[str, Any] | None:
    url = f"{s.ai_base_url}/chat/completions"
    body = {
        "model": s.ai_model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _SYS},
            {"role": "user", "content": f"Заголовок: {title}\nТекст: {summary or ''}"},
        ],
    }
    headers = {"Authorization": f"Bearer {s.ai_api_key}"}
    resp = await http.post(url, json=body, headers=headers)
    if resp is None or resp.status_code != 200:
        logger.warning("LLM-классификация: ответ %s", getattr(resp, "status_code", "none"))
        return None
    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        parsed["model"] = s.ai_model
        return _sanitize(parsed, "")
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        logger.warning("LLM-ответ не распарсен: %s", exc)
        return None


async def classify(
    title: str, summary: str | None, s: Settings, http: HttpClient, source: str = ""
) -> dict[str, Any]:
    if s.ai_enabled and s.ai_api_key:
        result = await _llm_classify(title, summary, s, http)
        if result is not None:
            return result
        logger.info("LLM недоступен — фолбэк на правила")
    return fallback_classify(title, summary, source)
