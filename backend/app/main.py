"""FastAPI-приложение ALTSR (API + WebSocket живой ленты)."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api.admin import router as admin_router
from .api.articles import router as articles_router
from .api.assistant import router as assistant_router
from .api.auth import router as auth_router
from .api.billing import router as billing_router
from .api.news import router as news_router
from .api.paper import router as paper_router
from .api.signals import router as signals_router
from .api.telegram import router as telegram_router
from .api.telegram import webhook_secret
from .api.tokens import router as tokens_router
from .api.user_paper import router as user_paper_router
from .config import get_settings
from .db import create_all
from .discovery.runner import PUBSUB_CHANNEL
from .redis_client import make_redis
from .schemas import HealthOut

logger = logging.getLogger("altsr.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_all()
    app.state.redis = await make_redis()
    # Зарегистрировать Telegram webhook, если задан токен бота.
    _s = get_settings()
    if _s.telegram_bot_token:
        with contextlib.suppress(Exception):
            from .notify.telegram import tg_set_webhook
            await tg_set_webhook(
                _s, f"{_s.site_url.rstrip('/')}/api/telegram/webhook", webhook_secret(_s)
            )
    yield
    if app.state.redis is not None:
        with contextlib.suppress(Exception):
            await app.state.redis.aclose()


app = FastAPI(title="ALTSR — Early Token Radar", version=__version__, lifespan=lifespan)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tokens_router)
app.include_router(signals_router)
app.include_router(paper_router)
app.include_router(user_paper_router)
app.include_router(telegram_router)
app.include_router(news_router)
app.include_router(articles_router)
app.include_router(auth_router)
app.include_router(billing_router)
app.include_router(assistant_router)
app.include_router(admin_router)


@app.get("/health", response_model=HealthOut)
async def health() -> HealthOut:
    return HealthOut(status="ok", version=__version__)


@app.websocket("/ws/tokens")
async def ws_tokens(ws: WebSocket) -> None:
    """Живая лента: ретранслирует Redis pub/sub-канал новых токенов.

    Дисклеймер отправляется первым сообщением — он есть во всех каналах UI.
    """
    await ws.accept()
    await ws.send_json(
        {
            "type": "disclaimer",
            "text": "Не инвест-рекомендация. Торговля новыми токенами — крайне "
            "высокий риск полной потери средств. ~98% новых токенов обнуляются.",
        }
    )
    redis = ws.app.state.redis
    if redis is None:
        await ws.send_json({"type": "info", "text": "live-лента недоступна (нет Redis)"})
        # Держим соединение, чтобы клиент не ребутился в цикле.
        try:
            while True:
                await asyncio.sleep(30)
                await ws.send_json({"type": "ping"})
        except WebSocketDisconnect:
            return

    pubsub = redis.pubsub()
    await pubsub.subscribe(PUBSUB_CHANNEL)
    try:
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=30)
            if msg and msg.get("type") == "message":
                await ws.send_json({"type": "new_token", "data": msg["data"]})
            else:
                await ws.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(PUBSUB_CHANNEL)
        with contextlib.suppress(Exception):
            await pubsub.aclose()
