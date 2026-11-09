"""Разбор RSS/Atom-ленты в список новостей (stdlib, без внешних зависимостей)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from xml.etree import ElementTree as ET  # noqa: S405 — парсим доверенные фиды

from ..discovery.base import HttpClient

logger = logging.getLogger("altsr.ai.feeds")


@dataclass
class FeedItem:
    source: str
    title: str
    url: str
    summary: str | None
    published_at: datetime | None


def _text(el) -> str | None:
    return el.text.strip() if el is not None and el.text else None


def _parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            dt = datetime.strptime(s.strip(), fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def parse_feed(xml_text: str, source: str) -> list[FeedItem]:
    items: list[FeedItem] = []
    try:
        root = ET.fromstring(xml_text)  # noqa: S314 — доверенные RSS-источники
    except ET.ParseError as exc:
        logger.warning("Не удалось разобрать фид %s: %s", source, exc)
        return items

    # RSS 2.0: channel/item ; Atom: entry
    rss_items = root.findall(".//item")
    if rss_items:
        for it in rss_items:
            link = _text(it.find("link"))
            title = _text(it.find("title"))
            if not link or not title:
                continue
            items.append(FeedItem(
                source=source, title=title, url=link,
                summary=_text(it.find("description")),
                published_at=_parse_date(_text(it.find("pubDate"))),
            ))
        return items

    ns = "{http://www.w3.org/2005/Atom}"
    for en in root.findall(f".//{ns}entry"):
        title = _text(en.find(f"{ns}title"))
        link_el = en.find(f"{ns}link")
        link = link_el.get("href") if link_el is not None else None
        if not link or not title:
            continue
        items.append(FeedItem(
            source=source, title=title, url=link,
            summary=_text(en.find(f"{ns}summary")),
            published_at=_parse_date(_text(en.find(f"{ns}updated"))),
        ))
    return items


async def fetch_feed(http: HttpClient, url: str, source: str) -> list[FeedItem]:
    text = await http.get_text(url)
    if text is None:
        return []
    return parse_feed(text, source)
