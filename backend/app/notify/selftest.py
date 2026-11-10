"""Самопроверка Telegram-уведомлений.

Запуск на сервере (нужен сетевой доступ): ``python -m app.notify.selftest``

Логика:
- Если TELEGRAM_CHAT_ID не задан — тянем getUpdates по токену бота и печатаем найденные
  chat_id. (Сначала напиши боту @Altsr_bot любое сообщение, затем запусти команду —
  увидишь свой chat_id, его и впиши в TELEGRAM_CHAT_ID.)
- Если chat_id задан — шлём тестовый системный алерт и подтверждаем доставку.

Секреты берутся только из окружения/.env. В коде их нет.
"""
from __future__ import annotations

import asyncio
import logging

from ..config import Settings, get_settings
from ..discovery.base import HttpClient
from .alerts import SystemAlerter

logger = logging.getLogger("altsr.notify.selftest")


async def resolve_chat_ids(settings: Settings, http: HttpClient) -> list[tuple[str, str]]:
    """Вернуть уникальные (chat_id, имя) из getUpdates. Пусто, если нет токена/сообщений."""
    if not settings.telegram_bot_token:
        return []
    url = f"{settings.telegram_api_base}/bot{settings.telegram_bot_token}/getUpdates"
    data = await http.get_json(url)
    found: list[tuple[str, str]] = []
    if isinstance(data, dict):
        for upd in data.get("result", []) or []:
            msg = upd.get("message") or upd.get("channel_post") or {}
            chat = msg.get("chat") or {}
            cid = chat.get("id")
            if cid is None:
                continue
            name = chat.get("title") or chat.get("username") or chat.get("first_name") or ""
            found.append((str(cid), str(name)))
    seen: set[str] = set()
    uniq: list[tuple[str, str]] = []
    for cid, name in found:
        if cid not in seen:
            seen.add(cid)
            uniq.append((cid, name))
    return uniq


async def run() -> int:
    """0 — успех (или подсказка выдана), 1 — отправка не удалась."""
    s = get_settings()
    if not s.telegram_bot_token:
        print("TELEGRAM_BOT_TOKEN не задан — впиши токен бота в .env.")
        return 1

    async with HttpClient(timeout=s.http_timeout_seconds) as http:
        if not s.telegram_chat_id:
            chats = await resolve_chat_ids(s, http)
            if chats:
                print("Найденные chat_id (впиши нужный в TELEGRAM_CHAT_ID):")
                for cid, name in chats:
                    print(f"  {cid}\t{name}")
            else:
                print("getUpdates пуст. Напиши боту @Altsr_bot любое сообщение и запусти снова.")
            return 0

        alerter = SystemAlerter(s)  # без Redis — дедуп не нужен для разовой проверки
        ok = await alerter.alert(
            "selftest",
            "✅ Тестовый системный алерт ALTSR — связь с Telegram работает.",
            severity="info",
            dedup_seconds=0,
            http=http,
        )
        print("Тестовый алерт отправлен." if ok
              else "Не удалось отправить (проверь токен/chat_id).")
        return 0 if ok else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s | %(message)s")
    raise SystemExit(asyncio.run(run()))
