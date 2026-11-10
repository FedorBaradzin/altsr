"""Обучение confidence на исходах сделок (T3, рычаг ④). Чистая логика, без сети/БД.

Накопленные (features → исход win/loss) калибруют веса логистической регрессии; из
них считается confidence. Нет данных/мало примеров → fallback на текущую эвристику
(решает вызывающий). Без внешних зависимостей — простой градиентный спуск на Python.

ВАЖНО: калибровка улучшает разделение win/loss на истории, но не гарантирует прибыль.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

# Фиксированный порядок признаков. Значения берутся из SignalInput (см. extract_features).
FEATURE_NAMES: tuple[str, ...] = (
    "roc_m5",       # % изменение m5 (проксирует ROC)
    "roc_h1",       # % изменение h1
    "buy_sell",     # buys/sells m5
    "liq_norm",     # ликвидность / 1e5 (грубая нормировка)
    "risk_inv",     # (100 - risk_score)/100 — выше = безопаснее
    "vol_norm",     # объём h1 / 1e5
)
N_FEATURES = len(FEATURE_NAMES)


@dataclass(frozen=True)
class Weights:
    """Веса логистической регрессии: смещение + коэффициенты по признакам."""

    bias: float
    coef: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.coef) != N_FEATURES:
            raise ValueError(f"нужно {N_FEATURES} коэффициентов, дано {len(self.coef)}")


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


def predict_proba(features: Sequence[float], w: Weights) -> float:
    """Вероятность win в [0, 1]."""
    z = w.bias + sum(c * x for c, x in zip(w.coef, features, strict=False))
    return _sigmoid(z)


def fit_logistic(
    x: Sequence[Sequence[float]],
    y: Sequence[int],
    *,
    lr: float = 0.1,
    epochs: int = 500,
    l2: float = 0.0,
    min_samples: int = 20,
) -> Weights | None:
    """Обучает веса градиентным спуском. Возвращает None при нехватке данных.

    None → вызывающий использует fallback (текущую формулу confidence).
    """
    n = len(x)
    if n < min_samples or n != len(y):
        return None
    if any(len(row) != N_FEATURES for row in x):
        raise ValueError("несогласованная размерность признаков")
    # Нужны оба класса, иначе разделять нечего.
    if len(set(y)) < 2:
        return None

    bias = 0.0
    coef = [0.0] * N_FEATURES
    for _ in range(epochs):
        g_bias = 0.0
        g_coef = [0.0] * N_FEATURES
        for row, label in zip(x, y, strict=False):
            z = bias + sum(c * v for c, v in zip(coef, row, strict=False))
            err = _sigmoid(z) - label
            g_bias += err
            for j in range(N_FEATURES):
                g_coef[j] += err * row[j]
        bias -= lr * g_bias / n
        for j in range(N_FEATURES):
            coef[j] -= lr * (g_coef[j] / n + l2 * coef[j])
    return Weights(bias=bias, coef=tuple(coef))


def extract_features(
    *,
    roc_m5: float | None,
    roc_h1: float | None,
    buys_m5: int | None,
    sells_m5: int | None,
    liquidity_usd: float | None,
    risk_score: int | None,
    vol_h1: float | None,
) -> list[float]:
    """Вектор признаков фиксированного порядка. Нет данных → нейтральные значения."""
    buy_sell = 1.0
    if buys_m5 is not None and sells_m5 is not None:
        buy_sell = buys_m5 / max(1, sells_m5)
    risk_inv = 0.5
    if risk_score is not None:
        risk_inv = max(0.0, (100 - risk_score) / 100.0)
    return [
        (roc_m5 or 0.0) / 100.0,
        (roc_h1 or 0.0) / 100.0,
        min(buy_sell, 10.0),
        min((liquidity_usd or 0.0) / 1e5, 10.0),
        risk_inv,
        min((vol_h1 or 0.0) / 1e5, 10.0),
    ]


def accuracy(x: Sequence[Sequence[float]], y: Sequence[int], w: Weights) -> float:
    """Доля верно классифицированных (порог 0.5) — для оценки качества калибровки."""
    if not x:
        return 0.0
    ok = 0
    for row, label in zip(x, y, strict=False):
        if (predict_proba(row, w) >= 0.5) == bool(label):
            ok += 1
    return ok / len(x)
