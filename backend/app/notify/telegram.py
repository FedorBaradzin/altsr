"""Отправка в Telegram. Без токена/чата — no-op (логирует и возвращает False)."""
from __future__ import annotations

import logging

from ..config import Settings
from ..discovery.base import HttpClient

logger = logging.getLogger("altsr.notify.telegram")


class TelegramNotifier:
    def __init__(self, settings: Settings) -> None:
        self.token = settings.telegram_bot_token
        self.chat_id = settings.telegram_chat_id
        self.api_base = settings.telegram_api_base
        self.timeout = settings.http_timeout_seconds

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    async def send(self, text: str, *, http: HttpClient | None = None) -> bool:
        if not self.enabled:
            logger.info("Telegram не настроен — пропускаю отправку")
            return False
        url = f"{self.api_base}/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        owns = http is None
        client = http or HttpClient(timeout=self.timeout)
        try:
            if owns:
                await client.__aenter__()
            resp = await client.post(url, json=payload)
            ok = resp is not None and resp.status_code == 200
            if not ok and resp is not None:
                logger.warning("Telegram ответил %s: %s", resp.status_code, resp.text[:200])
            return ok
        finally:
            if owns:
                await client.__aexit__(None, None, None)


async def send_to_chat(
    settings: Settings, chat_id: str, text: str, *, http: HttpClient | None = None
) -> bool:
    """Отправить сообщение в конкретный чат (личные алерты пользователя)."""
    if not settings.telegram_bot_token or not chat_id:
        return False
    url = f"{settings.telegram_api_base}/bot{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id, "text": text,
        "parse_mode": "HTML", "disable_web_page_preview": True,
    }
    owns = http is None
    client = http or HttpClient(timeout=settings.http_timeout_seconds)
    try:
        if owns:
            await client.__aenter__()
        resp = await client.post(url, json=payload)
        return resp is not None and resp.status_code == 200
    finally:
        if owns:
            await client.__aexit__(None, None, None)


async def tg_get_username(settings: Settings) -> str | None:
    """getMe → @username бота (для deep-link). None без токена/ошибке."""
    if not settings.telegram_bot_token:
        return None
    url = f"{settings.telegram_api_base}/bot{settings.telegram_bot_token}/getMe"
    try:
        async with HttpClient(timeout=settings.http_timeout_seconds) as http:
            data = await http.get_json(url)
        if data and data.get("ok"):
            return data["result"].get("username")
    except Exception as exc:  # noqa: BLE001
        logger.warning("getMe не удался: %s", exc)
    return None


async def tg_set_webhook(settings: Settings, webhook_url: str, secret: str) -> bool:
    """Зарегистрировать webhook у Telegram (вызывается на старте backend)."""
    if not settings.telegram_bot_token:
        return False
    url = f"{settings.telegram_api_base}/bot{settings.telegram_bot_token}/setWebhook"
    payload = {"url": webhook_url, "secret_token": secret, "allowed_updates": ["message"]}
    try:
        async with HttpClient(timeout=settings.http_timeout_seconds) as http:
            resp = await http.post(url, json=payload)
        return resp is not None and resp.status_code == 200
    except Exception as exc:  # noqa: BLE001
        logger.warning("setWebhook не удался: %s", exc)
        return False


async def notify_digest(
    settings: Settings, text: str, *, http: HttpClient | None = None
) -> bool:
    """Тонкий хук шины событий (T8): отправить дайджест/сессионную сводку в Telegram.

    No-op (возвращает False) без ``EVENTBUS_ENABLED`` или без настроенного Telegram —
    поведение существующих уведомлений не меняется.
    """
    if not settings.eventbus_enabled:
        return False
    return await TelegramNotifier(settings).send(text, http=http)
