"""Вход кошельком (EVM): nonce → подпись personal_sign → восстановление адреса.

Проверка подписи через eth_account (если установлен). Без него — честный отказ, чтобы
не пропускать вход без реальной проверки.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("altsr.auth.wallet")

LOGIN_MESSAGE = "ALTSR login\nСигнатура подтверждает вход. Nonce: {nonce}"


def build_message(nonce: str) -> str:
    return LOGIN_MESSAGE.format(nonce=nonce)


def verify_eth_signature(address: str, message: str, signature: str) -> bool:
    """True, если signature для message сделана владельцем address (EVM)."""
    try:
        from eth_account import Account
        from eth_account.messages import encode_defunct
    except ImportError:  # pragma: no cover
        logger.warning("eth_account не установлен — вход кошельком недоступен")
        return False
    try:
        recovered = Account.recover_message(encode_defunct(text=message), signature=signature)
        return recovered.lower() == address.lower()
    except Exception as exc:  # noqa: BLE001
        logger.info("Проверка подписи не удалась: %s", exc)
        return False
