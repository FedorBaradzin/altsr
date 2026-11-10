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
