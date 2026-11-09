"""Контент-движок: новость → ОРИГИНАЛЬНАЯ SEO-статья.

Важно (авторские права): НЕ воспроизводим текст источника. Пишем собственный разбор с
ссылкой-атрибуцией. LLM-путь при ключе; без ключа — детерминированный оригинальный шаблон
(чтобы пайплайн работал офлайн; для качественного SEO нужен LLM). Везде дисклеймер
«не инвест-рекомендация».
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from typing import Any

from ..config import Settings
from ..discovery.base import HttpClient

logger = logging.getLogger("altsr.ai.content")

DISCLAIMER = ("Disclaimer: this article is for information only, not financial advice. "
             "Trading new tokens is extremely high-risk — most new tokens go to zero.")


_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _translit(text: str) -> str:
    return "".join(_TRANSLIT.get(ch, _TRANSLIT.get(ch.lower(), ch)) for ch in text)


def slugify(text: str, max_len: int = 80) -> str:
    text = _translit(text)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9\s-]", "", text).strip().lower()
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:max_len].strip("-") or "article"


def _trim(s: str, n: int) -> str:
    s = s.strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def fallback_article(title: str, catalyst: str | None, source_name: str | None,
                     source_url: str | None, lang: str) -> dict[str, Any]:
    """Оригинальный шаблон (не копия источника). Короткий полезный разбор катализатора."""
    cat = (catalyst or "update").lower()
    topic = title.strip().rstrip(".")
    seo_title = _trim(f"{topic}: what it means for traders", 70)
    meta = _trim(f"A quick, neutral breakdown of {topic.lower()} and what new-token traders "
                 f"should check before acting. Screening over hype.", 155)
    how = {
        "listing": "A new listing can add liquidity and visibility, but it is not a quality signal on its own — check whether liquidity is locked and whether the contract is verified.",
        "exploit": "An exploit is a hard risk event. If you hold exposure, re-check the contract status and liquidity immediately; security issues can turn a position illiquid fast.",
        "unlock": "A token unlock increases circulating supply and can add sell pressure. Watch the unlock size relative to daily volume and existing liquidity.",
        "audit": "An audit lowers some contract risk but never removes it — detection catches part of the schemes, not all. Treat a clean audit as one input, not a guarantee.",
        "partnership": "A partnership can be a genuine catalyst or pure marketing. Verify it from the official source, not a forwarded post.",
        "delisting": "A delisting is a liquidity and access risk. Confirm it from the exchange directly and reassess any open exposure.",
    }.get(cat, "Treat any single headline as one input. Verify from the primary source before acting.")

    body = (
        f"# {topic}\n\n"
        f"New tokens move fast, and a single headline rarely tells the whole story. "
        f"Here is a neutral read on this {cat} event and what actually matters.\n\n"
        f"## What happened\n\n{topic}. "
        f"{'Reported via ' + source_name + '.' if source_name else ''}\n\n"
        f"## Why it matters\n\n{how}\n\n"
        f"## What to check before acting\n\n"
        f"- Is the contract verified and free of honeypot / high sell-tax flags?\n"
        f"- Is liquidity meaningful and locked?\n"
        f"- How concentrated is the top-holder supply?\n"
        f"- Does the move hold up on primary sources, or is it a forwarded rumor?\n\n"
        f"ALTSR screens brand-new tokens for these risks and simulates entries on paper before "
        f"anything touches real money. Screening reduces the risk of theft (scams), not the risk "
        f"that a token simply goes to zero.\n\n"
        + (f"Source: [{source_name or 'original report'}]({source_url})\n\n" if source_url else "")
        + f"_{DISCLAIMER}_\n"
    )
    keywords = f"{cat} crypto, new token {cat}, altcoin screening, crypto risk, {slugify(topic).replace('-', ' ')}"
    return {"title": seo_title, "meta_description": meta, "keywords": _trim(keywords, 390),
            "body": body, "model": "rules", "lang": lang}


def _sanitize(d: dict[str, Any], lang: str, source_name, source_url) -> dict[str, Any]:
    title = _trim(str(d.get("title") or "Market update"), 70)
    meta = _trim(str(d.get("meta_description") or title), 155)
    body = str(d.get("body") or "").strip()
    if source_url and "](" not in body:
        body += f"\n\nSource: [{source_name or 'original report'}]({source_url})\n"
    if "financial advice" not in body.lower():
        body += f"\n\n_{DISCLAIMER}_\n"
    kw = d.get("keywords")
    if isinstance(kw, list):
        kw = ", ".join(str(k) for k in kw)
    return {"title": title, "meta_description": meta, "keywords": _trim(str(kw or ""), 390),
            "body": body, "model": d.get("model", "llm"), "lang": lang}


_LANG_NAME = {"en": "English", "ru": "Russian", "es": "Spanish", "de": "German"}


async def _llm_article(title, summary, catalyst, lang, s, http, source_name, source_url):
    lang_name = _LANG_NAME.get(lang, lang)
    sys = (
        f"You are a crypto writer. Write an ORIGINAL SEO article in {lang_name} about the news below. "
        "Do NOT copy the source text — synthesize in your own words. Neutral, useful, no hype, "
        "no price predictions. Return strict JSON: "
        '{"title": "<=60 chars, keyword-rich", "meta_description": "<=155 chars", '
        '"keywords": "comma-separated", "body": "markdown ~550 words with ## subheads, '
        'end with a one-line not-financial-advice disclaimer"}.'
    )
    body = {
        "model": s.ai_model, "temperature": 0.4,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": sys},
            {"role": "user", "content": f"Headline: {title}\nSummary: {summary or ''}\n"
                                        f"Catalyst: {catalyst}\nSource: {source_name or ''} {source_url or ''}"},
        ],
    }
    resp = await http.post(f"{s.ai_base_url}/chat/completions", json=body,
                           headers={"Authorization": f"Bearer {s.ai_api_key}"})
    if resp is None or resp.status_code != 200:
        return None
    try:
        parsed = json.loads(resp.json()["choices"][0]["message"]["content"])
        parsed["model"] = s.ai_model
        return _sanitize(parsed, lang, source_name, source_url)
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        logger.warning("LLM-статья не распарсена: %s", exc)
        return None


async def generate_article(
    *, title: str, summary: str | None, catalyst: str | None,
    source_name: str | None, source_url: str | None, s: Settings, http: HttpClient,
    lang: str | None = None,
) -> dict[str, Any]:
    lang = lang or s.content_lang
    if s.ai_enabled and s.ai_api_key:
        res = await _llm_article(title, summary, catalyst, lang, s, http, source_name, source_url)
        if res is not None:
            return res
        logger.info("LLM для статьи недоступен — оригинальный шаблон")
    return fallback_article(title, catalyst, source_name, source_url, lang)
