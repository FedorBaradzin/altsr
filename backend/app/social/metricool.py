"""Планирование постов в соцсети через Metricool API.

Metricool — инструмент планирования/аналитики соцсетей (не консультант). Здесь мы ставим
наши SEO-статьи в расписание публикаций. Точные поля эндпоинта зависят от версии Metricool
API (см. их doc PDF) — вынесены в один payload, легко скорректировать.
"""
from __future__ import annotations

import logging

from ..config import Settings
from ..discovery.base import HttpClient

logger = logging.getLogger("altsr.social.metricool")


def build_post_text(title: str, url: str, keywords: str | None, max_len: int = 240) -> str:
    """Короткий текст поста: заголовок + ссылка + пара хэштегов."""
    tags = ""
    if keywords:
        words = [w.strip().replace(" ", "") for w in keywords.split(",")[:2] if w.strip()]
        tags = " " + " ".join(f"#{w}" for w in words if w.isascii() and w.isalnum())
    base = title.strip()
    room = max_len - len(url) - len(tags) - 2
    if len(base) > room:
        base = base[: room - 1].rstrip() + "…"
    return f"{base}\n{url}{tags}".strip()


async def schedule_post(
    http: HttpClient, s: Settings, *, text: str, when_iso: str, networks: list[str] | None = None,
) -> bool:
    """Поставить пост в расписание Metricool. True при успехе."""
    if not (s.metricool_user_token and s.metricool_user_id and s.metricool_blog_id):
        logger.warning("Metricool не настроен (token/user/blog) — пропуск")
        return False
    nets = networks or s.metricool_network_list
    url = (f"{s.metricool_base_url}/v2/scheduler/posts"
           f"?userId={s.metricool_user_id}&blogId={s.metricool_blog_id}"
           f"&userToken={s.metricool_user_token}")
    payload = {
        "text": text,
        "providers": [{"network": n} for n in nets],
        "publicationDate": {"dateTime": when_iso, "timezone": "UTC"},
        "autoPublish": True,
    }
    resp = await http.post(url, json=payload)
    ok = resp is not None and resp.status_code in (200, 201)
    if not ok:
        logger.warning("Metricool scheduling failed: %s", getattr(resp, "status_code", "none"))
    return ok
