"""Тарифы (из pricing.md). price_usd — месячная цена; 0 = бесплатный."""
from __future__ import annotations

TIERS: dict[str, dict] = {
    "free": {
        "name": "Free", "price_usd": 0,
        "features": ["Лента с задержкой", "Базовый вердикт безопасности",
                     "3 сигнала/день", "Демо бумажной торговли"],
    },
    "pro": {
        "name": "Pro", "price_usd": 49,
        "features": ["Real-time лента", "Полная риск-карточка", "Сигналы без лимита",
                     "Telegram-алерты", "Бумажный портфель", "История и фильтры"],
    },
    "autonomous": {
        "name": "Autonomous", "price_usd": 89,
        "features": ["Всё из Pro", "Подвязка Telegram (бот + уведомления)",
                     "Автоторговля (Delegation / Vault)", "Онлайн-поддержка 24/7",
                     "Прямая связь в Telegram", "Расширенный риск-контроль"],
    },
}

PAID_TIERS = [t for t in TIERS if TIERS[t]["price_usd"] > 0]


def tier_price(tier: str) -> float | None:
    t = TIERS.get(tier)
    return float(t["price_usd"]) if t else None
