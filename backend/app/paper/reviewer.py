"""Reviewer-стадия (T6): пост-трейд разбор, замыкающий конвейер.

Discover → Safety → Signal → Executor → **Reviewer**. После закрытия сделки:
  * считаем чистые агрегаты качества (win-rate, средний R, просадка, net P&L);
  * при убытке автоматически вносим токен в Redis-блеклист (TTL), чтобы не
    входить в него повторно, пока действует карантин.

Агрегаты — чистые функции над списком результатов (легко юнит-тестировать).
Блеклист — тонкая обёртка над Redis (ключ altsr:blacklist:{chain}:{address}).
ВСЁ БУМАЖНОЕ: reviewer ничего не исполняет, только анализирует и помечает.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from ..config import Settings

logger = logging.getLogger("altsr.paper.reviewer")


@dataclass(frozen=True)
class TradeResult:
    """Итог одной закрытой сделки (неизменяемый снимок для агрегатов)."""

    pnl_usd: float          # валовый P&L в USD
    r_multiple: float       # R-мультипликатор (P&L в единицах начального риска)
    net_after_costs: float  # чистый P&L после издержек (fee+spread+slippage)
    exit_reason: str        # причина выхода (hard stop / take profit / ...)


@dataclass(frozen=True)
class ReviewStats:
    """Сводные метрики качества по набору закрытых сделок."""

    trades: int
    win_rate: float
    avg_r: float
    max_drawdown: float
    net_pnl: float


# --- Чистые агрегаты ---------------------------------------------------------
def win_rate(results: Sequence[TradeResult]) -> float:
    """Доля прибыльных сделок (net_after_costs > 0). Пусто → 0.0."""
    if not results:
        return 0.0
    wins = sum(1 for r in results if r.net_after_costs > 0)
    return wins / len(results)


def avg_r(results: Sequence[TradeResult]) -> float:
    """Средний R-мультипликатор по сделкам. Пусто → 0.0."""
    if not results:
        return 0.0
    return sum(r.r_multiple for r in results) / len(results)


def net_pnl(results: Sequence[TradeResult]) -> float:
    """Суммарный чистый P&L после издержек. Пусто → 0.0."""
    return sum(r.net_after_costs for r in results)


def max_drawdown(results: Sequence[TradeResult]) -> float:
    """Макс. просадка кривой капитала (пик→дно) в USD, в порядке сделок.

    Считаем кумулятивный net P&L, отслеживаем бегущий пик и максимальное
    падение от него. Монотонно растущая кривая → 0.0.
    """
    peak = 0.0
    cumulative = 0.0
    drawdown = 0.0
    for r in results:
        cumulative += r.net_after_costs
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
    return drawdown


def summarize(results: Sequence[TradeResult]) -> ReviewStats:
    """Собрать все агрегаты за один проход-удобный вызов."""
    return ReviewStats(
        trades=len(results),
        win_rate=win_rate(results),
        avg_r=avg_r(results),
        max_drawdown=max_drawdown(results),
        net_pnl=net_pnl(results),
    )


# --- Redis-блеклист ----------------------------------------------------------
def _blacklist_key(chain: str, address: str) -> str:
    return f"altsr:blacklist:{chain}:{address}"


async def blacklist_token(
    redis, chain: str, address: str, ttl_seconds: int, reason: str
) -> None:
    """Внести токен в карантин на ttl_seconds. Без Redis — тихий no-op."""
    if redis is None:
        return
    key = _blacklist_key(chain, address)
    try:
        if ttl_seconds and ttl_seconds > 0:
            await redis.set(key, reason, ex=ttl_seconds)
        else:
            await redis.set(key, reason)
    except Exception as exc:  # noqa: BLE001 — блеклист не должен ронять конвейер
        logger.warning("Не удалось записать блеклист %s:%s (%s)", chain, address, exc)
        return
    logger.info("Токен %s:%s в блеклисте на %ss — %s", chain, address, ttl_seconds, reason)


async def is_blacklisted(redis, chain: str, address: str) -> bool:
    """True, если токен сейчас в карантине. Без Redis/при ошибке — False (не блокируем)."""
    if redis is None:
        return False
    try:
        return bool(await redis.exists(_blacklist_key(chain, address)))
    except Exception as exc:  # noqa: BLE001 — недоступность Redis не должна блокировать вход
        logger.warning("Проверка блеклиста недоступна (%s) — считаем чистым", exc)
        return False


def _is_loss(result: TradeResult) -> bool:
    """Сделка считается убыточной по чистому результату после издержек."""
    return result.net_after_costs < 0


# --- Ревью закрытой сделки ---------------------------------------------------
async def review_closed_trade(
    redis,
    settings: Settings,
    *,
    chain: str,
    address: str,
    result: TradeResult,
    history: Sequence[TradeResult] = (),
) -> ReviewStats:
    """Разобрать закрытую сделку: пересчитать агрегаты (history + новая сделка)
    и при убытке авто-внести токен в блеклист, когда включён BLACKLIST_ON_LOSS.

    Возвращает обновлённые метрики. Побочный эффект — только пометка в Redis.
    """
    stats = summarize([*history, result])
    if settings.blacklist_on_loss and _is_loss(result):
        await blacklist_token(
            redis, chain, address, settings.blacklist_ttl_seconds, result.exit_reason
        )
    return stats
