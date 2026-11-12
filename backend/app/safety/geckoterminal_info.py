"""GeckoTerminal token-info → SafetyFindings (репутационный сигнал).

Эндпоинт: GET {base}/networks/{network}/tokens/{address}/info
Отдаёт data.attributes с `gt_score` (0..100, выше = надёжнее) — той самой
репутацией, по которой GeckoTerminal в UI рисует плашку «Отмечен как скам-токен».
GoPlus мы читаем напрямую, но его token_security не покрывает все репортные/
репутационные кейсы площадки; низкий gt_score — независимый soft-сигнал.

Чистый парсер `parse_token_info` без сети (покрыт unit-тестами). Сетевой `fetch`
деградирует мягко: таймаут/ошибка/нет поля → SafetyFindings без данных (None),
что НЕ меняет вердикт.
"""
from __future__ import annotations

import logging
from typing import Any

from ..discovery.base import HttpClient
from ..discovery.geckoterminal import NETWORK_TO_CHAIN
from .base import SafetyFindings

logger = logging.getLogger("altsr.safety.gecko")

# Наши chain → имя сети в GeckoTerminal (обратное NETWORK_TO_CHAIN, канонично).
CHAIN_TO_NETWORK = {
    "ethereum": "eth",
    "base": "base",
    "bsc": "bsc",
    "polygon": "polygon_pos",
    "arbitrum": "arbitrum",
    "solana": "solana",
}


def _score(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        s = float(v)
    except (ValueError, TypeError):
        return None
    # gt_score нормирован 0..100; отбрасываем очевидный мусор.
    if s < 0 or s > 100:
        return None
    return s


def parse_token_info(addr: str, payload: Any, chain: str = "") -> SafetyFindings:
    """Достать gt_score из ответа token-info. Нет поля → reputation_score=None."""
    data = (payload or {}).get("data") if isinstance(payload, dict) else None
    attrs = (data or {}).get("attributes", {}) if isinstance(data, dict) else {}
    score = _score(attrs.get("gt_score"))
    return SafetyFindings(
        chain=chain,
        address=addr,
        reputation_score=score,
        sources=["geckoterminal"] if score is not None else [],
        raw={"geckoterminal_info": attrs} if attrs else {},
    )


async def fetch(http: HttpClient, base_url: str, chain: str, address: str) -> SafetyFindings:
    network = CHAIN_TO_NETWORK.get(chain) or next(
        (gt for gt, ch in NETWORK_TO_CHAIN.items() if ch == chain), None
    )
    if not network:
        logger.info("GeckoTerminal-safety: сеть %s не поддерживается", chain)
        return SafetyFindings(chain=chain, address=address)
    url = f"{base_url}/networks/{network}/tokens/{address}/info"
    try:
        payload = await http.get_json(url)
    except Exception as exc:  # noqa: BLE001
        logger.debug("GeckoTerminal-info %s:%s не получен: %s", chain, address, exc)
        return SafetyFindings(chain=chain, address=address)
    f = parse_token_info(address, payload, chain)
    f.chain = chain
    return f
