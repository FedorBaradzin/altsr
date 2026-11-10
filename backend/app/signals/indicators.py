"""Технические индикаторы (T1, рычаги ①③). Чистые функции, без сети/БД.

Работают на рядах цен/свечей (приходят из OHLCV-источника). Все функции
детерминированы и валидируют длину входа — «нет данных ≠ ноль».
"""
from __future__ import annotations

from collections.abc import Sequence


def roc(prices: Sequence[float], n: int) -> float:
    """Rate of Change, %: (p[-1] - p[-1-n]) / p[-1-n] * 100.

    Требует минимум n+1 значений и ненулевую базу.
    """
    if n < 1:
        raise ValueError("n должен быть ≥ 1")
    if len(prices) < n + 1:
        raise ValueError(f"нужно ≥ {n + 1} цен, получено {len(prices)}")
    base = prices[-1 - n]
    if base == 0:
        raise ValueError("базовая цена равна нулю")
    return (prices[-1] - base) / base * 100.0


def true_ranges(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]
) -> list[float]:
    """True Range для каждого бара, начиная со второго (нужен close[i-1])."""
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("highs/lows/closes должны быть одной длины")
    if len(closes) < 2:
        raise ValueError("нужно ≥ 2 баров")
    out: list[float] = []
    for i in range(1, len(closes)):
        prev_close = closes[i - 1]
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - prev_close),
            abs(lows[i] - prev_close),
        )
        out.append(tr)
    return out


def atr(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], n: int
) -> float:
    """Average True Range за n периодов (простое среднее последних n TR).

    Требует минимум n+1 баров (TR считается со второго бара).
    """
    if n < 1:
        raise ValueError("n должен быть ≥ 1")
    trs = true_ranges(highs, lows, closes)
    if len(trs) < n:
        raise ValueError(f"нужно ≥ {n + 1} баров, получено {len(closes)}")
    window = trs[-n:]
    return sum(window) / n


def aroon(
    highs: Sequence[float], lows: Sequence[float], n: int
) -> tuple[float, float]:
    """Aroon Up/Down (0..100) по окну из n+1 баров.

    up = 100 * (n - периодов_с_максимума) / n; down — симметрично по минимуму.
    """
    if n < 1:
        raise ValueError("n должен быть ≥ 1")
    if len(highs) != len(lows):
        raise ValueError("highs/lows должны быть одной длины")
    if len(highs) < n + 1:
        raise ValueError(f"нужно ≥ {n + 1} баров, получено {len(highs)}")
    win_h = list(highs[-(n + 1):])
    win_l = list(lows[-(n + 1):])
    last = n  # индекс последнего бара в окне
    # Самый свежий экстремум при равенстве (берём ближайший к текущему бару).
    hi_idx = max(range(n + 1), key=lambda i: (win_h[i], i))
    lo_idx = min(range(n + 1), key=lambda i: (win_l[i], -i))
    since_high = last - hi_idx
    since_low = last - lo_idx
    up = 100.0 * (n - since_high) / n
    down = 100.0 * (n - since_low) / n
    return up, down


def aroon_osc(highs: Sequence[float], lows: Sequence[float], n: int) -> float:
    """Aroon-осциллятор = up - down (от -100 до +100; >0 — восходящий тренд)."""
    up, down = aroon(highs, lows, n)
    return up - down
