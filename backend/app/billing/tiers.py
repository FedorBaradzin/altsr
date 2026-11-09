"""Тарифы (из pricing.md). price_usd — месячная цена; 0 = бесплатный."""
from __future__ import annotations

TIERS: dict[str, dict] = {
    "free": {
        "name": "Free", "price_usd": 0,
        "features": ["Лента с задержкой", "Базовый вердикт", "3 сигнала/день", "Демо бумаги"],
    },
    "pro": {
        "name": "Pro", "price_usd": 29,
        "features": ["Real-time лента", "Полная риск-карточка", "Сигналы без лимита",
                     "Telegram-алерты", "Бумажный портфель", "Рилсы сделок"],
    },
    "trader": {
        "name": "Trader", "price_usd": 79,
        "features": ["Всё из Pro", "Профили риска", "Несколько портфелей",
                     "Ранний доступ к сигналам", "API (лимит)", "Приоритетные источники"],
    },
    "team": {
        "name": "Team / API", "price_usd": 199,
        "features": ["Всё из Trader", "Полный API + SLA", "От 5 мест", "Приоритетная поддержка"],
    },
}

PAID_TIERS = [t for t in TIERS if TIERS[t]["price_usd"] > 0]


def tier_price(tier: str) -> float | None:
    t = TIERS.get(tier)
    return float(t["price_usd"]) if t else None
