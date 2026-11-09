"""Роут онлайн-консультанта 24/7."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends

from ..assistant.chat import answer
from ..config import Settings, get_settings
from ..discovery.base import HttpClient

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


@router.post("/chat")
async def chat(
    message: str = Body(..., embed=True),
    history: list[dict] = Body(default=[]),
    settings: Settings = Depends(get_settings),
) -> dict:
    messages = [*history[-8:], {"role": "user", "content": message}]
    async with HttpClient(timeout=settings.http_timeout_seconds) as http:
        reply = await answer(messages, settings, http)
    return {"answer": reply}
