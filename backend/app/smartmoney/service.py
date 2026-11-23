"""Оркестрация smart-money (анализ, НЕ торговля).

update_smart_money(): за цикл берёт ОГРАНИЧЕННЫЙ набор свежих PASS/trending
токенов, тянет их ончейн-сделки (GeckoTerminal, bounded concurrency),
выделяет ранних покупателей, апсертит записи покупателей (TokenBuyer),
пересчитывает для затронутых кошельков число ранних PASS-входов (SmartWallet)
и обновляет Token.smart_wallets.

Строго отказоустойчиво по месту вызова (runner оборачивает в try/except) и
бережёт rate-limit: лимит токенов за цикл, малый cap конкуренции, пропуск
недавно проверенных токенов (через Redis NX, как троттлинг Birdeye).

Только реальные данные: нет сделок → токен просто не даёт покупателей (0).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..discovery.base import HttpClient
from ..models import SafetyReport, SmartWallet, Token, TokenBuyer
from .gecko_trades import Trade, fetch_trades
from .heuristic import EarlyBuyer, extract_early_buyers, is_notable

if TYPE_CHECKING:
    from ..config import Settings
    from ..discovery.base import NormalizedToken

logger = logging.getLogger("altsr.smartmoney.service")

# Канонический chain (как в Token.chain) → имя сети GeckoTerminal для URL сделок.
# Обратное к discovery.geckoterminal.NETWORK_TO_CHAIN, но явно (без неоднозначности).
CHAIN_TO_NETWORK: dict[str, str] = {
    "ethereum": "eth",
    "base": "base",
    "bsc": "bsc",
    "polygon": "polygon_pos",
    "arbitrum": "arbitrum",
    "solana": "solana",
}

_CHECK_KEY = "smartmoney:checked:{chain}:{address}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _redis_should_check(redis, chain: str, address: str, ttl: int) -> bool:
    """True, если токен давно (или ни разу) не проверялся smart-money.

    Redis SET NX EX: первый за TTL видит True, повторы в пределах TTL — False.
    Нет Redis / ошибка → True (ограничение всё равно даёт лимит на цикл).
    """
    if redis is None or ttl <= 0:
        return True
    try:
        res = await redis.set(_CHECK_KEY.format(chain=chain, address=address), "1", nx=True, ex=ttl)
        return bool(res)
    except Exception as exc:  # noqa: BLE001 — троттлинг не должен ронять шаг
        logger.debug("Redis smart-money throttle недоступен (%s)", exc)
        return True


async def _pick_candidates(
    session: AsyncSession, settings: "Settings", redis
) -> list[Token]:
    """Свежие PASS-токены c pair_address в поддерживаемых сетях, bounded лимитом.

    Берём с запасом, затем пропускаем недавно проверенные (Redis) и обрезаем до
    smartmoney_max_tokens_per_cycle.
    """
    max_tokens = max(1, settings.smartmoney_max_tokens_per_cycle)
    networks = CHAIN_TO_NETWORK.keys()
    rows = (
        await session.execute(
            select(Token)
            .join(SafetyReport, SafetyReport.token_id == Token.id)
            .where(
                SafetyReport.verdict == "PASS",
                Token.pair_address.is_not(None),
                Token.chain.in_(networks),
            )
            .order_by(Token.discovered_at.desc())
            .limit(max_tokens * 4)
        )
    ).scalars().all()

    picked: list[Token] = []
    for tok in rows:
        if not tok.pair_address:
            continue
        if await _redis_should_check(
            redis, tok.chain, tok.address, settings.smartmoney_recheck_seconds
        ):
            picked.append(tok)
        if len(picked) >= max_tokens:
            break
    return picked


async def _fetch_all_trades(
    http: HttpClient,
    settings: "Settings",
    candidates: list[Token],
) -> dict[int, list[Trade]]:
    """Параллельно (с cap конкуренции) забрать сделки по каждому кандидату.

    Возвращает {token_id: trades}. Сетевые вызовы делаем конкурентно, но
    запись в БД — последовательно вне этой функции (AsyncSession не потокобезопасна).
    """
    sem = asyncio.Semaphore(max(1, settings.smartmoney_concurrency))

    async def _one(tok: Token) -> tuple[int, list[Trade]]:
        network = CHAIN_TO_NETWORK.get(tok.chain)
        if not network or not tok.pair_address:
            return tok.id, []
        async with sem:
            try:
                trades = await fetch_trades(
                    http, settings.gecko_base_url, network, tok.pair_address
                )
            except Exception as exc:  # noqa: BLE001 — один токен не валит остальные
                logger.debug("trades %s:%s недоступны: %s", tok.chain, tok.address, exc)
                return tok.id, []
        return tok.id, trades

    results = await asyncio.gather(*(_one(t) for t in candidates), return_exceptions=True)
    out: dict[int, list[Trade]] = {}
    for res in results:
        if isinstance(res, Exception):
            logger.debug("сбор сделок упал: %s", res)
            continue
        token_id, trades = res
        out[token_id] = trades
    return out


async def _upsert_token_buyers(
    session: AsyncSession, tok: Token, buyers: list[EarlyBuyer]
) -> None:
    """Апсерт ранних покупателей токена (уникальность по token_id+wallet)."""
    for b in buyers:
        existing = (
            await session.execute(
                select(TokenBuyer).where(
                    TokenBuyer.token_id == tok.id,
                    TokenBuyer.wallet_address == b.wallet,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            # Уточняем ранг/время, если новые данные «раньше».
            if b.rank < existing.rank:
                existing.rank = b.rank
            if existing.bought_at is None and b.ts is not None:
                existing.bought_at = b.ts
            existing.verdict_pass = True
            continue
        session.add(
            TokenBuyer(
                token_id=tok.id,
                wallet_address=b.wallet,
                chain=tok.chain,
                rank=b.rank,
                volume_usd=b.volume_usd,
                verdict_pass=True,
                bought_at=b.ts,
            )
        )


async def _early_pass_count(session: AsyncSession, wallet: str) -> int:
    """Сколько РАЗНЫХ PASS-токенов этот кошелёк купил рано (живой join с safety)."""
    return int(
        (
            await session.execute(
                select(func.count(func.distinct(TokenBuyer.token_id)))
                .join(SafetyReport, SafetyReport.token_id == TokenBuyer.token_id)
                .where(
                    TokenBuyer.wallet_address == wallet,
                    SafetyReport.verdict == "PASS",
                )
            )
        ).scalar_one()
        or 0
    )


async def _recompute_wallets(
    session: AsyncSession, settings: "Settings", wallets: set[str], now: datetime
) -> None:
    """Пересчитать early_pass_count/notable для затронутых кошельков (SmartWallet)."""
    min_pass = settings.smartmoney_min_pass_for_notable
    for wallet in wallets:
        count = await _early_pass_count(session, wallet)
        notable = is_notable(count, min_pass)
        sw = (
            await session.execute(
                select(SmartWallet).where(SmartWallet.address == wallet)
            )
        ).scalar_one_or_none()
        if sw is None:
            session.add(
                SmartWallet(
                    address=wallet,
                    early_pass_count=count,
                    notable=notable,
                    first_seen_at=now,
                    updated_at=now,
                )
            )
        else:
            sw.early_pass_count = count
            sw.notable = notable
            sw.updated_at = now


async def _recompute_token_smart_wallets(session: AsyncSession, token_ids: list[int]) -> None:
    """Для каждого токена: smart_wallets = число РАЗНЫХ notable-кошельков, купивших рано."""
    for token_id in token_ids:
        cnt = int(
            (
                await session.execute(
                    select(func.count(func.distinct(TokenBuyer.wallet_address)))
                    .join(SmartWallet, SmartWallet.address == TokenBuyer.wallet_address)
                    .where(
                        TokenBuyer.token_id == token_id,
                        SmartWallet.notable.is_(True),
                    )
                )
            ).scalar_one()
            or 0
        )
        tok = await session.get(Token, token_id)
        if tok is not None:
            tok.smart_wallets = cnt


async def update_smart_money(
    session: AsyncSession,
    settings: "Settings",
    http: HttpClient,
    tokens: "list[NormalizedToken] | None" = None,
    *,
    redis=None,
) -> int:
    """Главная точка входа smart-money шага. Возвращает число обработанных токенов.

    `tokens` (свежий сбор discovery) принимается для совместимости сигнатуры, но
    кандидаты берутся из БД (нужны token_id + актуальный verdict PASS). Шаг
    идемпотентен и целиком отказоустойчив у вызывающего (runner обёртывает try/except).
    """
    now = _utcnow()
    candidates = await _pick_candidates(session, settings, redis)
    if not candidates:
        return 0

    trades_by_token = await _fetch_all_trades(http, settings, candidates)

    touched_wallets: set[str] = set()
    processed_ids: list[int] = []
    early_n = settings.smartmoney_early_trades

    for tok in candidates:
        trades = trades_by_token.get(tok.id) or []
        processed_ids.append(tok.id)
        if not trades:
            continue
        buyers = extract_early_buyers(trades, early_n)
        if not buyers:
            continue
        await _upsert_token_buyers(session, tok, buyers)
        touched_wallets.update(b.wallet for b in buyers)

    # flush, чтобы пересчёт видел только что добавленные TokenBuyer.
    await session.flush()
    await _recompute_wallets(session, settings, touched_wallets, now)
    await session.flush()
    # Пересчитываем smart_wallets не только у обработанных в этом цикле токенов,
    # но и у ВСЕХ токенов, купленных затронутыми кошельками в прошлых циклах:
    # кошелёк мог стать notable только сейчас, а токены он покупал раньше —
    # без этого их счётчик навсегда остаётся 0 (баг эвентуальной консистентности).
    affected_ids: set[int] = set(processed_ids)
    if touched_wallets:
        rows = await session.execute(
            select(TokenBuyer.token_id)
            .where(TokenBuyer.wallet_address.in_(list(touched_wallets)))
            .distinct()
        )
        affected_ids.update(int(r[0]) for r in rows.all())
    await _recompute_token_smart_wallets(session, list(affected_ids))
    await session.commit()

    logger.info(
        "smart-money: обработано %d токенов, затронуто %d кошельков",
        len(processed_ids), len(touched_wallets),
    )
    return len(processed_ids)
