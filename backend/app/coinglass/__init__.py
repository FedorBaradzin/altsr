"""Coinglass — МАКРО-источник режима рынка (деривативы BTC/ETH + весь рынок).

Это НЕ детектор микрокап-токенов. Coinglass даёт агрегаты по фьючерсам —
funding rate, open interest, ликвидации, long/short ratio — из которых мы
считаем простой «market regime» (risk_on / neutral / risk_off / unknown).

Режим — ОПЦИОНАЛЬНЫЙ мягкий вход, по умолчанию ВЫКЛ (coinglass_enabled=False),
и он НИКОГДА не является жёстким гейтом торговли. Ключ берётся только из env.
"""
from __future__ import annotations

from .client import CoinglassClient
from .regime import compute_regime, market_regime_ok

__all__ = ["CoinglassClient", "compute_regime", "market_regime_ok"]
