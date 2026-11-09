"""Ответ консультанта: LLM при ключе, иначе FAQ-фолбэк.

Жёсткие правила в system-промте: никаких инвест-рекомендаций и прогнозов цены, всегда
дисклеймер, только про ALTSR. При сбое LLM — откат на FAQ.
"""
from __future__ import annotations

import logging

from ..config import Settings
from ..discovery.base import HttpClient
from .faq import answer_from_faq

logger = logging.getLogger("altsr.assistant")

SYSTEM = (
    "Ты — онлайн-консультант платформы ALTSR (ранний радар новых криптотокенов). "
    "Отвечай кратко, дружелюбно и только по теме ALTSR: анти-скам скрининг (вердикты "
    "PASS/REVIEW/BLOCK + risk-score), сигналы на вход, бумажная симуляция, тарифы, как начать. "
    "ЖЁСТКИЕ ПРАВИЛА: никогда не давай инвест-рекомендаций и не прогнозируй цену; если спрашивают "
    "«что купить» или «вырастет ли» — вежливо объясни, что ты таких советов не даёшь. Всегда "
    "подчёркивай, что это скрининг и симуляция, ~98% новых токенов обнуляются. Не выдумывай факты "
    "вне ALTSR. Отвечай на языке пользователя. Держи ответ в пределах пары абзацев."
)

MAX_HISTORY = 8


async def answer(messages: list[dict], s: Settings, http: HttpClient) -> str:
    """messages: [{role:'user'|'assistant', content:str}]. Возвращает текст ответа."""
    last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")

    if not (s.ai_enabled and s.ai_api_key):
        return answer_from_faq(last_user)

    convo = [{"role": "system", "content": SYSTEM}]
    for m in messages[-MAX_HISTORY:]:
        role = "assistant" if m.get("role") == "assistant" else "user"
        convo.append({"role": role, "content": str(m.get("content", ""))[:2000]})

    resp = await http.post(
        f"{s.ai_base_url}/chat/completions",
        json={"model": s.ai_model, "temperature": 0.3, "messages": convo},
        headers={"Authorization": f"Bearer {s.ai_api_key}"},
    )
    if resp is None or resp.status_code != 200:
        logger.info("LLM-консультант недоступен — FAQ-фолбэк")
        return answer_from_faq(last_user)
    try:
        return resp.json()["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, ValueError, TypeError):
        return answer_from_faq(last_user)
