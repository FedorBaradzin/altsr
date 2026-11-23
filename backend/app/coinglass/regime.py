"""Простой, объяснимый расчёт «режима рынка» из деривативов Coinglass.

Чистая функция compute_regime() берёт уже полученные данные (4 ряда) и выдаёт::

    {
      "regime": "risk_on" | "neutral" | "risk_off" | "unknown",
      "score":  -1.0 .. 1.0,   # >0 risk_on, <0 risk_off
      "signals": {funding, oi_change, liquidation_spike, long_short},
      "as_of":  iso8601 | None,
    }

Эвристика (намеренно простая и задокументированная, НЕ инвест-рекомендация):
  • funding > 0 (лонги платят) и растущий OI → толпа в лонгах, перегрев → risk_off-крен.
  • отрицательный funding + тяжёлые ЛОНГ-ликвидации → капитуляция/вымывание → risk_off.
  • умеренно положительный funding, спокойные ликвидации, L/S около 1 → risk_on/neutral.
Нет данных по сигналу → поле null, в score не учитывается. Если валидных сигналов
нет вовсе → regime="unknown". НИКОГДА не выдумываем значения.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ..config import Settings
from ..discovery.base import to_float

logger = logging.getLogger("altsr.coinglass.regime")

# Порог «спайка» ликвидаций: во сколько раз последний бар превышает средний.
LIQ_SPIKE_RATIO = 2.0
# Порог «перегретого» funding для нормировки сигнала к [-1,1]. Единица — та, что
# отдаёт Coinglass funding-rate/exchange-list (наблюдаемо ~percent: 0.01 ≈ 0.01%).
# Подбирается на сервере; положительный funding → крен в risk_off.
FUNDING_HOT = 0.03
# Границы классификации итогового score.
RISK_ON_AT = 0.25
RISK_OFF_AT = -0.25


def _last(rows: list[dict] | None) -> dict | None:
    return rows[-1] if rows else None


def _num(row: dict | None, *keys: str) -> float | None:
    """Достать первое доступное числовое поле из row по списку возможных имён."""
    if not row:
        return None
    for k in keys:
        if k in row:
            v = to_float(row[k])
            if v is not None:
                return v
    return None


def _as_of(*rows: list[dict] | None) -> str | None:
    """ISO-время самого свежего бара среди переданных рядов (поле time/t/ts)."""
    best: float | None = None
    for r in rows:
        last = _last(r)
        t = _num(last, "time", "t", "ts", "createTime")
        if t is None:
            continue
        secs = t / 1000 if t > 10_000_000_000 else t
        best = secs if best is None else max(best, secs)
    if best is None:
        return None
    try:
        return datetime.fromtimestamp(best, tz=timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def _avg_exchange_funding(funding: list[dict] | None) -> float | None:
    """Средний funding_rate по биржам из confirmed exchange-list.

    Форма: data[] c полем stablecoin_margin_list[] = [{exchange, funding_rate}, ...].
    Берём среднее funding_rate по всем биржам (стейбл-маржинальным); иначе None.
    """
    if not funding:
        return None
    rates: list[float] = []
    for entry in funding:
        if not isinstance(entry, dict):
            continue
        margin_lists = (
            entry.get("stablecoin_margin_list")
            or entry.get("token_margin_list")
            or []
        )
        for ex in margin_lists:
            if isinstance(ex, dict):
                r = to_float(ex.get("funding_rate"))
                if r is not None:
                    rates.append(r)
    if rates:
        return sum(rates) / len(rates)
    return None


def _funding_signal(funding: list[dict] | None) -> float | None:
    """Знаковый вклад funding: сильно положительный (перегрев лонгов) → риск вниз.

    Понимает две формы: confirmed exchange-list (stablecoin_margin_list[].funding_rate)
    и OHLC-историю (close/fundingRate) как запасной вариант.
    """
    val = _avg_exchange_funding(funding)
    if val is None:
        row = _last(funding)
        val = _num(row, "close", "c", "fundingRate", "rate", "value")
    if val is None:
        return None
    # Нормируем к [-1,1] по порогу перегрева; положительный funding → отрицательный вклад.
    scaled = max(-1.0, min(1.0, val / FUNDING_HOT))
    return -scaled


def _oi_signal(oi: list[dict] | None) -> float | None:
    """Вклад изменения OI: рост OI сам по себе нейтрален, но усиливает funding-перегрев.

    Возвращаем относительное изменение close за ряд в [-1,1] (справочный сигнал).
    """
    if not oi or len(oi) < 2:
        return None
    first = _num(oi[0], "close", "c", "openInterest", "value")
    last = _num(oi[-1], "close", "c", "openInterest", "value")
    if not first or last is None:
        return None
    change = (last - first) / first
    return max(-1.0, min(1.0, change))


def _liquidation_signal(liq: list[dict] | None) -> dict[str, Any] | None:
    """Спайк ликвидаций: какая сторона вымывается и во сколько раз сильнее среднего.

    long-спайк → risk_off (принудительные продажи), short-спайк → risk_on (сквиз вверх).
    """
    if not liq:
        return None
    longs = [
        _num(r, "longLiquidationUsd", "longLiquidation", "aggregatedLongLiquidationUsd")
        for r in liq
    ]
    shorts = [
        _num(r, "shortLiquidationUsd", "shortLiquidation", "aggregatedShortLiquidationUsd")
        for r in liq
    ]
    longs = [x for x in longs if x is not None]
    shorts = [x for x in shorts if x is not None]
    if not longs or not shorts:
        return None
    last_long, last_short = longs[-1], shorts[-1]
    avg_long = sum(longs) / len(longs)
    avg_short = sum(shorts) / len(shorts)
    long_spike = avg_long > 0 and last_long / avg_long >= LIQ_SPIKE_RATIO
    short_spike = avg_short > 0 and last_short / avg_short >= LIQ_SPIKE_RATIO
    contrib = 0.0
    if long_spike:
        contrib -= 0.6
    if short_spike:
        contrib += 0.4
    return {
        "last_long_usd": round(last_long, 2),
        "last_short_usd": round(last_short, 2),
        "long_spike": long_spike,
        "short_spike": short_spike,
        "contrib": contrib,
    }


def _long_short_signal(ls: list[dict] | None) -> dict[str, Any] | None:
    """L/S-соотношение счетов: сильный перекос в лонги → толпа переполнена → риск вниз."""
    row = _last(ls)
    ratio = _num(row, "longShortRatio", "ratio", "longShortAccountRatio")
    if ratio is None:
        long_acc = _num(row, "longAccount", "longAccountRatio")
        short_acc = _num(row, "shortAccount", "shortAccountRatio")
        if long_acc is not None and short_acc:
            ratio = long_acc / short_acc
    if ratio is None:
        return None
    # ratio>1 → больше лонгов. Контртрендовый вклад: перегруженные лонги → риск вниз.
    contrib = max(-0.5, min(0.5, -(ratio - 1.0)))
    return {"ratio": round(ratio, 3), "contrib": contrib}


def compute_regime(
    *,
    funding: list[dict] | None,
    open_interest: list[dict] | None,
    liquidations: list[dict] | None,
    long_short: list[dict] | None,
) -> dict[str, Any]:
    """Свести 4 ряда деривативов в простой объяснимый режим рынка."""
    f_sig = _funding_signal(funding)
    oi_sig = _oi_signal(open_interest)
    liq_sig = _liquidation_signal(liquidations)
    ls_sig = _long_short_signal(long_short)

    contribs: list[float] = []
    if f_sig is not None:
        # funding-перегрев усиливается ростом OI (толпа заходит в ту же сторону).
        weight = 1.0 + (0.5 if (oi_sig is not None and oi_sig > 0) else 0.0)
        contribs.append(max(-1.0, min(1.0, f_sig * weight)))
    if liq_sig is not None:
        contribs.append(liq_sig["contrib"])
    if ls_sig is not None:
        contribs.append(ls_sig["contrib"])

    signals = {
        "funding": round(f_sig, 4) if f_sig is not None else None,
        "oi_change": round(oi_sig, 4) if oi_sig is not None else None,
        "liquidation_spike": liq_sig,
        "long_short": ls_sig,
    }
    as_of = _as_of(funding, open_interest, liquidations, long_short)

    if not contribs:
        return {"regime": "unknown", "score": 0.0, "signals": signals, "as_of": as_of}

    score = max(-1.0, min(1.0, sum(contribs) / len(contribs)))
    if score >= RISK_ON_AT:
        regime = "risk_on"
    elif score <= RISK_OFF_AT:
        regime = "risk_off"
    else:
        regime = "neutral"
    return {"regime": regime, "score": round(score, 3), "signals": signals, "as_of": as_of}


async def fetch_regime(settings: Settings, *, symbol: str = "BTC") -> dict[str, Any]:
    """Собрать данные из Coinglass и вернуть режим. Выключено/нет ключа → unknown.

    Никогда не бросает: при любой проблеме соответствующий сигнал = null.
    """
    base = {"regime": "unknown", "score": 0.0,
            "signals": {"funding": None, "oi_change": None,
                        "liquidation_spike": None, "long_short": None},
            "as_of": None, "symbol": symbol, "enabled": settings.coinglass_enabled}
    if not settings.coinglass_enabled or not settings.coinglass_api_key:
        return base

    from .client import CoinglassClient

    try:
        async with CoinglassClient(settings) as cg:
            funding = await cg.funding_rate(symbol)
            oi = await cg.open_interest(symbol)
            liq = await cg.liquidations(symbol)
            ls = await cg.long_short_ratio(symbol)
    except Exception:  # noqa: BLE001 — макро-фильтр не должен ронять вызывающий слой.
        logger.exception("Coinglass fetch_regime(%s) упал — возвращаю unknown", symbol)
        return base

    out = compute_regime(
        funding=funding, open_interest=oi, liquidations=liq, long_short=ls
    )
    out.update({"symbol": symbol, "enabled": True})
    return out


async def market_regime_ok(settings: Settings, *, symbol: str = "BTC") -> bool | None:
    """ОПЦИОНАЛЬНЫЙ мягкий хук для будущего: макро-режим «не против входа»?

    Возвращает:
      • None  — фильтр выключен / нет ключа / режим unknown → НЕ влиять на решение;
      • False — risk_off (толпа перегружена лонгами / тяжёлые лонг-ликвидации);
      • True  — neutral или risk_on.

    СЕЙЧАС НИКЕМ НЕ ВЫЗЫВАЕТСЯ в торговом пути: это доступный помощник, который
    другие слои МОГУТ подключить позже как мягкий вклад (не жёсткий гейт).
    """
    if not settings.coinglass_enabled:
        return None
    data = await fetch_regime(settings, symbol=symbol)
    regime = data.get("regime")
    if regime == "unknown":
        return None
    return regime != "risk_off"
