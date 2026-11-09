"""Безопасный каркас живого исполнения. По умолчанию НИЧЕГО не исполняет.

Многослойные предохранители (все должны пройти, иначе отказ):
1. LIVE_TRADING_ENABLED=true (по умолчанию false).
2. Настроены кошелёк и приватный RPC.
3. Задан дневной лимит трат и лимит на сделку (> 0).
4. Пройдена safety-проверка (вердикт PASS) + повторная honeypot-симуляция перед покупкой.
5. Явное подтверждение сделки (или в рамках дневного лимита, если подтверждение отключено).
6. Симуляция транзакции перед отправкой.

Реальный swap-адаптер (Jupiter/0x/1inch) намеренно оставлен заглушкой, которая бросает
NotImplementedError — чтобы код не мог молча двинуть реальные средства без осознанного
подключения кошелька и адаптера. Это осознанное решение безопасности, не недоработка.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ..config import Settings

logger = logging.getLogger("altsr.live.executor")


class LiveTradingDisabled(RuntimeError):
    """Живое исполнение выключено или не прошло предохранители."""


@dataclass
class LivePreflight:
    allowed: bool
    reason: str


def preflight(
    s: Settings,
    *,
    verdict: str | None,
    honeypot_ok: bool,
    trade_usd: float,
    confirmed: bool,
) -> LivePreflight:
    """Проверить все предохранители. Возвращает allowed + причину отказа."""
    if not s.live_trading_enabled:
        return LivePreflight(False, "LIVE_TRADING_ENABLED=false — живая торговля выключена")
    if not s.live_wallet_address or not s.live_private_rpc:
        return LivePreflight(False, "не настроены кошелёк и приватный RPC")
    if s.live_daily_cap_usd <= 0 or s.live_max_trade_usd <= 0:
        return LivePreflight(False, "не заданы дневной лимит и лимит на сделку")
    if trade_usd > s.live_max_trade_usd:
        return LivePreflight(False, f"сумма ${trade_usd:.0f} > лимита ${s.live_max_trade_usd:.0f}")
    if verdict != "PASS":
        return LivePreflight(False, f"safety-вердикт {verdict} ≠ PASS")
    if not honeypot_ok:
        return LivePreflight(False, "honeypot-симуляция не пройдена")
    if s.live_require_confirmation and not confirmed:
        return LivePreflight(False, "нет подтверждения сделки")
    return LivePreflight(True, "ok")


async def simulate_tx() -> bool:
    """Симуляция транзакции перед отправкой. Заглушка — подключить к RPC при активации."""
    return True


async def submit_swap(*_args, **_kwargs) -> str:
    """Реальный своп. Намеренно НЕ реализован — активировать с осознанным подключением."""
    raise NotImplementedError(
        "Живой swap-адаптер (Jupiter/0x/1inch) не подключён. "
        "Активировать после живого прогона: подключить кошелёк, адаптер и приватный RPC."
    )


async def attempt_live_buy(
    s: Settings,
    *,
    verdict: str | None,
    honeypot_ok: bool,
    trade_usd: float,
    confirmed: bool = False,
) -> str:
    """Единственная точка входа живой покупки. Отказывает, пока не пройдены ВСЕ предохранители."""
    pf = preflight(s, verdict=verdict, honeypot_ok=honeypot_ok,
                   trade_usd=trade_usd, confirmed=confirmed)
    if not pf.allowed:
        logger.warning("Live-покупка отклонена: %s", pf.reason)
        raise LiveTradingDisabled(pf.reason)
    if not await simulate_tx():
        raise LiveTradingDisabled("симуляция транзакции не прошла")
    return await submit_swap()  # дойдёт сюда только при осознанной активации
