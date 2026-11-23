"""Публичный read-only эндпоинт МАКРО-режима рынка (Coinglass деривативы).

GET /api/coinglass/regime — отдаёт объяснимый режим рынка (risk_on/neutral/
risk_off/unknown) по BTC-деривативам. Это справочный макро-сигнал для UI,
НЕ инвест-рекомендация и НЕ жёсткий гейт торговли.

Гейтинг: ПУБЛИЧНО (как /api/public/*), т.к. это агрегированные рыночные данные
без пользовательских/приватных сведений — выбран более лёгкий вариант доступа.
Если фильтр выключен или нет ключа — вернётся regime="unknown", enabled=false
(эндпоинт не падает и не раскрывает наличие/отсутствие ключа деталями).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..config import Settings, get_settings
from ..coinglass.regime import fetch_regime

router = APIRouter(prefix="/api/coinglass", tags=["coinglass"])


@router.get("/regime")
async def coinglass_regime(
    symbol: str = Query(default="BTC", min_length=1, max_length=20),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Макро-режим рынка по деривативам. Публичный, graceful (никогда не 5xx)."""
    data = await fetch_regime(settings, symbol=symbol.upper())
    data["disclaimer"] = (
        "Макро-режим рынка по деривативам — справочный сигнал, не инвест-"
        "рекомендация и не гарантия. Торговля сопряжена с высоким риском."
    )
    return data
