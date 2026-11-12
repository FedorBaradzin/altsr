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
from . import cross_source, geckoterminal_info, goplus, honeypot_is, rugcheck
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

    # Доп. репутационный сигнал GeckoTerminal (gt_score) — для EVM и Solana.
    if settings.gecko_safety_enabled:
        providers.append(
            geckoterminal_info.fetch(http, settings.gecko_base_url, chain, address)
        )

    results = await asyncio.gather(*providers, return_exceptions=True)

    # Сохраняем находки каждого провайдера отдельно — нужно для кросс-проверки (T10),
    # и параллельно сливаем в общий merged для скоринга. Падение одного провайдера
    # (исключение) не валит скрининг: просто пропускаем его.
    provider_findings: list[SafetyFindings] = []
    merged = SafetyFindings(chain=chain, address=address)
    for res in results:
        if isinstance(res, Exception):
            logger.warning("safety-провайдер упал для %s:%s — %s", chain, address, res)
            continue
        provider_findings.append(res)
        merged.merge(res)
    merged.chain = chain
    merged.address = address

    result = evaluate(
        merged,
        require_lp_lock_solana=settings.safety_solana_require_lp_lock,
        gecko_min_score=(
            settings.gecko_safety_min_score if settings.gecko_safety_enabled else None
        ),
    )

    # T10: кросс-проверка двух независимых провайдеров. Расхождение → REVIEW.
    # Деградирует мягко: если выжил лишь один провайдер — single_source без штрафа.
    if settings.cross_source_enabled and provider_findings:
        agreement = cross_source.cross_check(
            provider_findings[0],
            provider_findings[1] if len(provider_findings) > 1 else None,
            penalty=settings.cross_source_confidence_penalty,
        )
        result = cross_source.apply_agreement(result, agreement)

    return result


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
