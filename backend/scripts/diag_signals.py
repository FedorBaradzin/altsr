"""Диагностика воронки сигналов: реплика _candidates + evaluate_entry над текущим
батчем, со сводкой причин отказа по сетям. Read-only. Запуск:
  docker compose exec -T signals python - < /tmp/diag.py
"""
import asyncio
import collections
from datetime import datetime, timezone

from sqlalchemy import case, func, select

from app.config import get_settings
from app.db import get_sessionmaker
from app.discovery.base import HttpClient
from app.models import SafetyReport, Signal, Token
from app.signals.engine import SignalInput, evaluate_entry
from app.signals.momentum import fetch_momentum
from app.signals.runner import _age_minutes


async def main() -> None:
    s = get_settings()
    now = datetime.now(timezone.utc)
    print("CFG mom_enabled", s.momentum_enabled, "require_data", s.momentum_require_data,
          "min_m5", s.momentum_min_change_m5, "min_h1", s.momentum_min_change_h1,
          "min_liq", s.signal_min_liquidity_usd, "batch", s.signal_batch_size,
          "gecko_trades", s.signal_gecko_trades_enabled)
    async with get_sessionmaker()() as session:
        src = func.lower(func.coalesce(Token.source, ""))
        priority = case((src.like("%geckoterminal_top%"), 0), (src.like("%trending%"), 0), else_=1)
        stmt = (
            select(Token, SafetyReport)
            .join(SafetyReport, SafetyReport.token_id == Token.id)
            .outerjoin(Signal, Signal.token_id == Token.id)
            .where(Signal.id.is_(None))
        )
        if s.signal_require_pass:
            stmt = stmt.where(SafetyReport.verdict == "PASS")
        stmt = stmt.order_by(priority, Token.discovered_at.desc()).limit(s.signal_batch_size)
        rows = (await session.execute(stmt)).all()
        print("BATCH size", len(rows), "chains", dict(collections.Counter(t.chain for t, _ in rows)))

        rej: collections.Counter = collections.Counter()
        passed = 0
        bychain_pass: collections.Counter = collections.Counter()
        async with HttpClient(timeout=s.http_timeout_seconds, max_retries=s.http_max_retries) as http:
            for token, rep in rows:
                mom = None
                if s.momentum_enabled:
                    try:
                        mom = await fetch_momentum(http, s.dexscreener_base_url, token.chain, token.address)
                    except Exception:  # noqa: BLE001
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
                if d.passed:
                    passed += 1
                    bychain_pass[token.chain] += 1
                else:
                    # нормализуем причину (убираем числа) для группировки
                    key = (d.rejected or "?")
                    for ch in "0123456789":
                        key = key.replace(ch, "")
                    rej[key[:46]] += 1
        print("PASSED", passed, "by chain", dict(bychain_pass))
        print("TOP REJECTIONS:")
        for k, v in rej.most_common(14):
            print("  ", v, "x", k)


asyncio.run(main())
