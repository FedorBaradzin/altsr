"""GoPlus Security API → SafetyFindings (EVM + Solana).

EVM:    GET {base}/token_security/{chain_id}?contract_addresses={addr}
Solana: GET {base}/solana/token_security?contract_addresses={addr}
Без ключа (есть rate-limit). Значения часто строки "0"/"1"/"" — парсим осторожно.
"""
from __future__ import annotations

import logging
from typing import Any

from ..discovery.base import HttpClient
from .base import SafetyFindings

logger = logging.getLogger("altsr.safety.goplus")

# Наши chain → GoPlus chain_id (EVM).
GOPLUS_CHAIN_ID = {
    "ethereum": "1",
    "bsc": "56",
    "base": "8453",
    "polygon": "137",
    "arbitrum": "42161",
    "optimism": "10",
    "avalanche": "43114",
}


def _b(v: Any) -> bool | None:
    """GoPlus bool: "1"→True, "0"→False, ""/None→None."""
    if v is None or v == "":
        return None
    s = str(v).strip()
    if s in ("1", "true", "True"):
        return True
    if s in ("0", "false", "False"):
        return False
    return None


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _i(v: Any) -> int | None:
    f = _f(v)
    return int(f) if f is not None else None


def _fake_token(v: Any) -> bool | None:
    """GoPlus fake_token: объект {value:0/1} или плоский флаг."""
    if v is None:
        return None
    if isinstance(v, dict):
        return _b(v.get("value"))
    return _b(v)


def _top_holder_pct(data: dict) -> float | None:
    """Макс. доля не-пулового, не-сожжённого холдера."""
    holders = data.get("holders") or []
    best: float | None = None
    for h in holders:
        tag = (h.get("tag") or "").lower()
        is_locked = _b(h.get("is_locked")) or False
        # Пропускаем пулы ликвидности, burn-адреса, залоченное.
        if any(k in tag for k in ("lp", "pool", "burn", "dead", "lock")) or is_locked:
            continue
        pct = _f(h.get("percent"))
        if pct is not None and (best is None or pct > best):
            best = pct
    return best


def _lp_locked(data: dict) -> tuple[bool | None, float | None]:
    lp = data.get("lp_holders") or []
    if not lp:
        return None, None
    locked = 0.0
    for h in lp:
        if _b(h.get("is_locked")):
            locked += _f(h.get("percent")) or 0.0
    return (locked > 0.5), locked


def parse_evm(addr: str, data: dict) -> SafetyFindings:
    top = _top_holder_pct(data)
    lp_locked, lp_pct = _lp_locked(data)
    return SafetyFindings(
        address=addr.lower(),
        is_honeypot=_b(data.get("is_honeypot")),
        buy_tax=_f(data.get("buy_tax")),
        sell_tax=_f(data.get("sell_tax")),
        is_open_source=_b(data.get("is_open_source")),
        mint_authority_active=_b(data.get("is_mintable")),
        owner_can_change_balance=_b(data.get("owner_change_balance")),
        owner_can_take_ownership=_b(data.get("can_take_back_ownership"))
        or _b(data.get("hidden_owner")),
        can_blacklist=_b(data.get("is_blacklisted")) or _b(data.get("transfer_pausable")),
        is_proxy=_b(data.get("is_proxy")),
        lp_locked=lp_locked,
        lp_locked_pct=lp_pct,
        top_holder_pct=top,
        holder_count=_i(data.get("holder_count")),
        is_true_token=_b(data.get("is_true_token")),
        # Явные сигналы «вредоносный/скам» — то, по чему помечают malicious.
        is_airdrop_scam=_b(data.get("is_airdrop_scam")),
        honeypot_same_creator=_b(data.get("honeypot_with_same_creator")),
        cannot_sell_all=_b(data.get("cannot_sell_all")),
        cannot_buy=_b(data.get("cannot_buy")),
        is_fake_token=_fake_token(data.get("fake_token")),
        tax_modifiable=_b(data.get("slippage_modifiable"))
        or _b(data.get("personal_slippage_modifiable")),
        trading_cooldown=_b(data.get("trading_cooldown")),
        sources=["goplus"],
        raw={"goplus": data},
    )


def parse_solana(addr: str, data: dict) -> SafetyFindings:
    # Solana-структура GoPlus: authority-поля вложены.
    mint = data.get("mintable") or {}
    freeze = data.get("freezable") or {}
    return SafetyFindings(
        address=addr,
        mint_authority_active=_b(mint.get("status")),
        freeze_authority_active=_b(freeze.get("status")),
        holder_count=_i(data.get("holder_count")),
        top_holder_pct=_top_holder_pct(data),
        sources=["goplus"],
        raw={"goplus_solana": data},
    )


async def fetch(http: HttpClient, base_url: str, chain: str, address: str) -> SafetyFindings:
    if chain == "solana":
        url = f"{base_url}/solana/token_security"
        payload = await http.get_json(url, params={"contract_addresses": address})
        result = (payload or {}).get("result", {})
        data = result.get(address) or (next(iter(result.values()), {}) if result else {})
        return parse_solana(address, data) if data else SafetyFindings(address=address)

    chain_id = GOPLUS_CHAIN_ID.get(chain)
    if not chain_id:
        logger.info("GoPlus: сеть %s не поддерживается", chain)
        return SafetyFindings(chain=chain, address=address)
    url = f"{base_url}/token_security/{chain_id}"
    payload = await http.get_json(url, params={"contract_addresses": address})
    result = (payload or {}).get("result", {})
    data = result.get(address.lower()) or (next(iter(result.values()), {}) if result else {})
    f = parse_evm(address, data) if data else SafetyFindings(address=address.lower())
    f.chain = chain
    return f
