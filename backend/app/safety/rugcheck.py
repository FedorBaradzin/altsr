"""RugCheck полный отчёт (Solana) → SafetyFindings.

GET {base}/tokens/{mint}/report
Поля: mintAuthority, freezeAuthority, rugged, risks[], markets[].lp.lpLockedPct,
topHolders[].pct, totalHolders. Форма ответа может меняться — парсим осторожно.
"""
from __future__ import annotations

import logging
from typing import Any

from ..discovery.base import HttpClient
from .base import SafetyFindings

logger = logging.getLogger("altsr.safety.rugcheck")


def _top_holder_pct(data: dict) -> float | None:
    holders = data.get("topHolders") or []
    best: float | None = None
    for h in holders:
        if h.get("insider") is True:
            pass  # инсайдера учитываем в концентрации
        # RugCheck отдаёт pct как проценты (0..100) → в доли.
        pct = h.get("pct")
        if pct is None:
            continue
        try:
            frac = float(pct) / 100.0  # RugCheck pct в процентах
        except (ValueError, TypeError):
            continue
        # Пропускаем явные пулы/LP.
        if (h.get("owner") or "").lower() in ("", "pool") or h.get("isLp"):
            continue
        if best is None or frac > best:
            best = frac
    return best


def _lp_locked(data: dict) -> tuple[bool | None, float | None]:
    markets = data.get("markets") or []
    best_locked: float | None = None
    for m in markets:
        lp = m.get("lp") or {}
        val = lp.get("lpLockedPct")
        if val is None:
            continue
        try:
            frac = float(val) / 100.0  # lpLockedPct в процентах
        except (ValueError, TypeError):
            continue
        if best_locked is None or frac > best_locked:
            best_locked = frac
    if best_locked is None:
        return None, None
    return (best_locked > 0.5), best_locked


def parse_report(mint: str, data: dict) -> SafetyFindings:
    lp_locked, lp_pct = _lp_locked(data)
    # authority активна, если поле присутствует и не null/пусто.
    nulls = (None, "", "null")
    mint_active = (data.get("mintAuthority") not in nulls) if "mintAuthority" in data else None
    freeze_active = (
        (data.get("freezeAuthority") not in nulls) if "freezeAuthority" in data else None
    )
    rugged = data.get("rugged") if isinstance(data.get("rugged"), bool) else None
    holders = data.get("totalHolders")
    return SafetyFindings(
        chain="solana",
        address=mint,
        mint_authority_active=mint_active,
        freeze_authority_active=freeze_active,
        rugged=rugged,
        lp_locked=lp_locked,
        lp_locked_pct=lp_pct,
        top_holder_pct=_top_holder_pct(data),
        holder_count=holders if isinstance(holders, int) else None,
        sources=["rugcheck"],
        raw={"rugcheck": _compact(data)},
    )


def _compact(data: dict) -> dict[str, Any]:
    """Не тащим в БД весь ответ — только ключевое."""
    return {
        "score": data.get("score"),
        "rugged": data.get("rugged"),
        "risks": [r.get("name") for r in (data.get("risks") or []) if r.get("name")],
    }


async def fetch(http: HttpClient, base_url: str, mint: str) -> SafetyFindings:
    url = f"{base_url}/tokens/{mint}/report"
    payload = await http.get_json(url)
    if not isinstance(payload, dict):
        return SafetyFindings(chain="solana", address=mint)
    return parse_report(mint, payload)
