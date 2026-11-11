"""Рыночная динамика: всплеск объёма и давление покупок (чистые функции).

Отдельный модуль, без БД/сети — полностью тестируется и переиспользуется и в
гейтах входа, и во вкладе в уверенность.

Семантика:
- buy_pressure_ratio — отношение buys/sells за m5 при достаточном числе сделок.
- volume_spike_ratio — во сколько раз текущий часовой объём выше БАЗОВОГО
  (среднего за предыдущие часы). Отличается от оборота vol/liq (это «насколько
  активно торгуется относительно пула») и от булева «объём растёт» (vol_h1 >
  vol_h1_prev): всплеск ловит аномальный скачок активности как градиент.
- volume_spike_bonus — неотрицательный вклад всплеска в уверенность [0..weight].

ВАЖНО: всплеск объёма повышает ожидаемую ценность и качество РАНЖИРОВАНИЯ уже
прошедших ворота входов. Это НЕ гарантия прибыли и не «сигнал на рост» —
большинство новых токенов идут в ноль, а всплеск бывает и на сливе.
"""
from __future__ import annotations

# Минимум сделок за m5, ниже которого отношение buys/sells статистически шумное.
_MIN_TRADES = 5
# Число предыдущих часов, по которым усредняется база, когда известен vol_h6.
_PRIOR_HOURS = 5.0


def buy_pressure_ratio(
    buys_m5: int | None, sells_m5: int | None, *, min_trades: int = _MIN_TRADES
) -> float | None:
    """buys/sells за m5. None, если данных нет или сделок слишком мало.

    Делитель защищён max(1, sells): при нулевых продажах отношение = числу покупок.
    """
    if buys_m5 is None or sells_m5 is None:
        return None
    if buys_m5 + sells_m5 < min_trades:
        return None
    return buys_m5 / max(1, sells_m5)


def volume_spike_ratio(
    vol_h1: float | None,
    vol_h6: float | None = None,
    vol_h1_prev: float | None = None,
) -> float | None:
    """Отношение текущего часового объёма к базовому за предыдущие часы.

    База (в порядке предпочтения):
    1. (vol_h6 - vol_h1) / 5 — средний объём ПРЕДЫДУЩИХ 5 часов (vol_h6 включает
       текущий час, поэтому вычитаем его), если это значение положительно;
    2. vol_h1_prev — предыдущий часовой срез, если известен и положителен.
    None, если нет текущего объёма или не из чего построить базу.
    """
    if vol_h1 is None:
        return None
    baseline: float | None = None
    if vol_h6 is not None and vol_h6 > vol_h1:
        prior = (vol_h6 - vol_h1) / _PRIOR_HOURS
        if prior > 0:
            baseline = prior
    if baseline is None and vol_h1_prev is not None and vol_h1_prev > 0:
        baseline = vol_h1_prev
    if baseline is None or baseline <= 0:
        return None
    return vol_h1 / baseline


def volume_spike_bonus(ratio: float | None, *, ref: float, weight: float) -> float:
    """Градуированный вклад всплеска в уверенность [0..weight].

    0 при ratio ≤ 1 (нет всплеска), линейный рост до weight при ratio ≥ ref.
    ref — во сколько раз объём должен превысить базу для полного вклада (напр. 3×).
    None (нет данных) → 0.
    """
    if ratio is None:
        return 0.0
    denom = max(1e-9, ref - 1.0)
    frac = (ratio - 1.0) / denom
    frac = min(1.0, max(0.0, frac))
    return weight * frac
