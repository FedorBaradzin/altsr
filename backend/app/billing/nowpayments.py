"""NOWPayments: создание инвойса + проверка подписи IPN (вебхука).

IPN подписывается HMAC-SHA512 от JSON тела с ключами, отсортированными по алфавиту
(рекурсивно), без лишних пробелов. Сверяем с заголовком x-nowpayments-sig.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

from ..config import Settings
from ..discovery.base import HttpClient

logger = logging.getLogger("altsr.billing.nowpayments")


def _sorted_json(obj: Any) -> str:
    """Рекурсивно отсортировать ключи и сериализовать без пробелов (как NOWPayments)."""
    def norm(o):
        if isinstance(o, dict):
            return {k: norm(o[k]) for k in sorted(o)}
        if isinstance(o, list):
            return [norm(x) for x in o]
        return o
    return json.dumps(norm(obj), separators=(",", ":"), ensure_ascii=False)


def ipn_signature(payload: dict, ipn_secret: str) -> str:
    return hmac.new(ipn_secret.encode(), _sorted_json(payload).encode(), hashlib.sha512).hexdigest()


def verify_ipn(payload: dict, signature: str | None, ipn_secret: str) -> bool:
    if not ipn_secret or not signature:
        return False
    expected = ipn_signature(payload, ipn_secret)
    return hmac.compare_digest(expected, signature)


async def create_invoice(
    http: HttpClient, s: Settings, *, tier: str, price_usd: float, order_id: str,
    success_url: str, cancel_url: str, ipn_url: str,
) -> dict | None:
    """Создать инвойс. Возвращает {id, invoice_url} или None."""
    if not s.nowpayments_api_key:
        logger.warning("NOWPAYMENTS_API_KEY не задан — оплата недоступна")
        return None
    body = {
        "price_amount": price_usd, "price_currency": "usd",
        "order_id": order_id, "order_description": f"ALTSR {tier} subscription",
        "ipn_callback_url": ipn_url, "success_url": success_url, "cancel_url": cancel_url,
    }
    resp = await http.post(f"{s.nowpayments_base_url}/invoice", json=body,
                           headers={"x-api-key": s.nowpayments_api_key})
    if resp is None or resp.status_code not in (200, 201):
        logger.warning("NOWPayments invoice failed: %s", getattr(resp, "status_code", "none"))
        return None
    data = resp.json()
    return {"id": str(data.get("id")), "invoice_url": data.get("invoice_url")}


# Статусы NOWPayments, означающие успешную оплату.
PAID_STATES = {"finished", "confirmed", "sending"}
