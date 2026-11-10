"""Оркестратор safety_screen: источники → merge → scoring → БД.

Для EVM: GoPlus + honeypot.is. Для Solana: GoPlus(solana) + RugCheck.
Провайдеры вызываются параллельно; падение одного не валит скрининг.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..discovery.base import HttpClient
from ..models import SafetyReport, Token
from . import goplus, honeypot_is, rugcheck
from .base import SafetyFindings, SafetyResult
from .scoring import evaluate

logger = logging.getLogger("altsr.safety.screener")

EVM_CHAINS = set(goplus.GOPLUS_CHAIN_ID.keys())


async def screen_token(
    http: HttpClient, settings: Settings, chain: str, address: str
) -> SafetyResult:
    if chain == "solana":
        # RugCheck's /report endpoint currently returns 400 for most mints and
        # its retries stall the whole batch (~8s/token) → screening falls behind
        # and fresh coins never get a verdict. GoPlus(solana) covers the core
        # checks, so rely on it and only add RugCheck when explicitly enabled.
        providers = [goplus.fetch(http, settings.goplus_base_url, chain, address)]
        if settings.rugcheck_enabled:
            providers.append(rugcheck.fetch(http, settings.rugcheck_base_url, address))
    else:
        providers = [
            goplus.fetch(http, settings.goplus_base_url, chain, address),
            honeypot_is.fetch(http, settings.honeypot_base_url, chain, address),
        ]

    results = await asyncio.gather(*providers, return_exceptions=True)

    merged = SafetyFindings(chain=chain, address=address)
    for res in results:
        if isinstance(res, Exception):
            logger.warning("safety-провайдер упал для %s:%s — %s", chain, address, res)
            continue
        merged.merge(res)
    merged.chain = chain
    merged.address = address
    return evaluate(merged)


async def store_result(session: AsyncSession, token: Token, result: SafetyResult) -> SafetyReport:
    existing = (
        await session.execute(select(SafetyReport).where(SafetyReport.token_id == token.id))
    ).scalar_one_or_none()

    red_flags_json = json.dumps(result.red_flags_as_dicts(), ensure_ascii=False)
    findings_json = json.dumps(result.findings.raw, ensure_ascii=False)[:8000]
    sources = ",".join(result.findings.sources)
    now = datetime.now(timezone.utc)

    if existing is not None:
        existing.risk_score = result.risk_score
        existing.verdict = result.verdict
        existing.red_flags = red_flags_json
        existing.findings = findings_json
        existing.sources = sources
        existing.created_at = now
        report = existing
    else:
        report = SafetyReport(
            token_id=token.id,
            chain=result.chain,
            address=result.address,
            risk_score=result.risk_score,
            verdict=result.verdict,
            red_flags=red_flags_json,
            findings=findings_json,
            sources=sources,
            created_at=now,
        )
        session.add(report)

    await session.flush()
    await session.commit()
    return report


async def unscored_tokens(session: AsyncSession, limit: int) -> list[Token]:
    """Токены без отчёта безопасности, самые новые первыми."""
    stmt = (
        select(Token)
        .outerjoin(SafetyReport, SafetyReport.token_id == Token.id)
        .where(SafetyReport.id.is_(None))
        .order_by(Token.discovered_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())
