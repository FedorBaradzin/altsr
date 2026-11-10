"""Strategy Engine + реестр (ТЗ §5).

Чистый детерминированный слой: жизненный цикл стратегии CANDIDATE→…→CLOSED,
версионированный реестр и движок решений. Каждое решение несёт снимок рынка,
основание входа, план выхода и результат Risk Engine — для воспроизводимости и
аудита. Без сети; работа с БД вынесена в `store.py`.

ВАЖНО: «стратегия выдала вход» — это прохождение правил скрининга, а не гарантия
прибыли. Новые токены бывают неликвидными и мошенническими и могут обесцениться.
"""
from __future__ import annotations

from .engine import decide
from .lifecycle import IllegalTransition, StrategyEvent, next_state
from .registry import StrategyRegistry
from .types import (
    EntryRationale,
    ExitPlan,
    MarketSnapshot,
    StrategyAction,
    StrategyDecision,
    StrategyDefinition,
    StrategyState,
    StrategyVersion,
)

__all__ = [
    "decide",
    "IllegalTransition",
    "StrategyEvent",
    "next_state",
    "StrategyRegistry",
    "EntryRationale",
    "ExitPlan",
    "MarketSnapshot",
    "StrategyAction",
    "StrategyDecision",
    "StrategyDefinition",
    "StrategyState",
    "StrategyVersion",
]
