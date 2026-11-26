"""Полный путь Solana-кандидата: evaluate_entry → buy-pressure (Gecko trades) →
пере-проверка safety. Показывает, на каком шаге Solana-сигнал умирает. Read-only.
  docker compose exec -T signals python - < /tmp/diags.py
"""
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select

from app.config import get_settings
from app.db import get_sessionmaker
from app.discovery.base import HttpClient
from app.discovery.geckoterminal import chain_to_network, fetch_pool_trades
from app.models import SafetyReport, Signal, Token
from app.safety.screener import screen_token
from app.signals.engine import SignalInput, evaluate_entry
from app.signals.momentum import fetch_momentum
from app.signals.runner import _age_minutes


async def main() -> None:
    s = get_settings()
    now = datetime.now(timezone.utc)
    print("recheck_before_send", s.signal_recheck_safety_before_send,
          "gecko_trades", s.signal_gecko_trades_enabled,
          "min_bp", s.signal_min_buy_pressure, "min_buyers", s.signal_min_trade_buyers)
    async with get_sessionmaker()() as session:
        stmt = (
            select(Token, SafetyReport)
            .join(SafetyReport, SafetyReport.token_id == Token.id)
            .outerjoin(Signal, Signal.token_id == Token.id)
            .where(Signal.id.is_(None), SafetyReport.verdict == "PASS", Token.chain == "solana")
        )
        if s.signal_min_liquidity_usd > 0:
            stmt = stmt.where(Token.liquidity_usd.is_not(None), Token.liquidity_usd >= s.signal_min_liquidity_usd)
        if s.signal_max_age_minutes > 0:
            stmt = stmt.where(or_(Token.created_at.is_(None), Token.created_at >= now - timedelta(minutes=s.signal_max_age_minutes)))
        stmt = stmt.order_by(Token.discovered_at.desc()).limit(10)
        rows = (await session.execute(stmt)).all()
        print("SOLANA eligible candidates:", len(rows))
        async with HttpClient(timeout=s.http_timeout_seconds, max_retries=s.http_max_retries) as http:
            for token, rep in rows:
                mom = None
                if s.momentum_enabled:
                    try:
                        mom = await fetch_momentum(http, s.dexscreener_base_url, token.chain, token.address)
                    except Exception:
                        mom = None
                inp = SignalInput(
                    chain=token.chain, address=token.address, liquidity_usd=token.liquidity_usd,
                    age_minutes=_age_minutes(token, now), verdict=rep.verdict, risk_score=rep.risk_score,
                    smart_wallets=getattr(token, "smart_wallets", None),
                    is_trending=any(k in (token.source or "").lower() for k in ("trending", "top")),
                    price_change_m5=getattr(mom, "price_change_m5", None),
                    price_change_h1=getattr(mom, "price_change_h1", None),
                    vol_h1=getattr(mom, "vol_h1", None), vol_h6=getattr(mom, "vol_h6", None),
                    buys_m5=getattr(mom, "buys_m5", None), sells_m5=getattr(mom, "sells_m5", None),
                )
                d = evaluate_entry(inp, s)
                sym = (token.symbol or token.address[:6])
                if not d.passed:
                    print(f"  {sym}: EVAL-REJECT {d.rejected}")
                    continue
                # buy-pressure
                bp = None
                buyers = None
                net = chain_to_network(token.chain)
                pool = token.pair_address or token.address
                if s.signal_gecko_trades_enabled and net and pool:
                    try:
                        agg = await fetch_pool_trades(http, s.onchain_base_url, net, pool,
                                                      window_minutes=s.signal_gecko_trades_window_min,
                                                      headers=s.onchain_headers)
                        bp = agg.buy_pressure
                        buyers = agg.buyers
                    except Exception as e:
                        print(f"  {sym}: TRADES-ERR {e}")
                bp_block = (bp is not None and (bp < s.signal_min_buy_pressure or (buyers or 0) < s.signal_min_trade_buyers))
                # recheck safety
                fresh_verdict = "(skipped)"
                if s.signal_recheck_safety_before_send:
                    try:
                        fresh = await screen_token(http, s, token.chain, token.address)
                        fresh_verdict = f"{fresh.verdict}{'/mal' if fresh.is_malicious else ''}"
                    except Exception as e:
                        fresh_verdict = f"ERR {e}"
                verdict = "WOULD-EMIT" if (not bp_block and (fresh_verdict in ("(skipped)", "PASS"))) else "BLOCKED"
                print(f"  {sym}: EVAL-PASS bp={bp} buyers={buyers} bp_block={bp_block} recheck={fresh_verdict} => {verdict}")


asyncio.run(main())
