"""Pydantic v2 схемы для API."""
from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field


class TokenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chain: str
    address: str
    symbol: str | None
    name: str | None
    created_at: datetime | None
    liquidity_usd: float | None
    fdv: float | None
    pair_address: str | None
    dex: str | None
    socials: str | None
    source: str
    discovered_at: datetime
    last_seen_at: datetime
    seen_count: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def links(self) -> dict:
        """socials из JSON-строки → объект для фронтенда."""
        if not self.socials:
            return {}
        try:
            return json.loads(self.socials)
        except (ValueError, TypeError):
            return {}


# Коды «вредоносный/скам» (источник истины — SafetyResult.MALICIOUS_CODES).
_MALICIOUS_CODES = frozenset({
    "honeypot", "airdrop_scam", "honeypot_same_creator",
    "cannot_sell_all", "fake_token", "rugged",
})


def is_malicious_flags(flags: list) -> bool:
    """True → токен помечен как скам (для красной плашки в UI)."""
    return any(isinstance(f, dict) and f.get("code") in _MALICIOUS_CODES for f in flags)


class TokenWithSafety(TokenOut):
    verdict: str | None = None
    risk_score: int | None = None
    signal_confidence: float | None = None
    is_malicious: bool = False


class TokenList(BaseModel):
    items: list[TokenWithSafety]
    total: int
    limit: int
    offset: int


class SignalOut(BaseModel):
    id: int
    token_id: int
    chain: str
    address: str
    side: str
    confidence: float
    status: str
    created_at: datetime
    symbol: str | None = None
    reasons: list = []
    venues: list = []

    @classmethod
    def from_signal(cls, sig, symbol: str | None = None) -> SignalOut:
        def _j(s):
            try:
                return json.loads(s) if s else []
            except (ValueError, TypeError):
                return []
        return cls(
            id=sig.id, token_id=sig.token_id, chain=sig.chain, address=sig.address,
            side=sig.side, confidence=sig.confidence, status=sig.status,
            created_at=sig.created_at, symbol=symbol,
            reasons=_j(sig.reasons), venues=_j(sig.venues),
        )


class SignalList(BaseModel):
    items: list[SignalOut]
    total: int


class VenuesOut(BaseModel):
    chain: str
    address: str
    options: list = []


class PaperPositionOut(BaseModel):
    id: int
    chain: str
    address: str
    symbol: str | None
    status: str
    size_usd: float
    entry_price: float
    last_price: float
    peak_price: float
    remaining_fraction: float
    realized_pnl_usd: float
    pnl_pct: float | None
    exit_reason: str | None
    current_value_usd: float
    unrealized_pnl_usd: float
    opened_at: datetime
    closed_at: datetime | None

    @classmethod
    def from_position(cls, p) -> PaperPositionOut:
        if p.status == "open" and p.entry_price:
            current = p.size_usd * p.remaining_fraction * (p.last_price / p.entry_price)
            unreal = current - p.size_usd * p.remaining_fraction
        else:
            current = 0.0
            unreal = 0.0
        return cls(
            id=p.id, chain=p.chain, address=p.address, symbol=p.symbol, status=p.status,
            size_usd=p.size_usd, entry_price=p.entry_price, last_price=p.last_price,
            peak_price=p.peak_price, remaining_fraction=p.remaining_fraction,
            realized_pnl_usd=round(p.realized_pnl_usd, 2), pnl_pct=p.pnl_pct,
            exit_reason=p.exit_reason, current_value_usd=round(current, 2),
            unrealized_pnl_usd=round(unreal, 2), opened_at=p.opened_at, closed_at=p.closed_at,
        )


class PaperSummaryOut(BaseModel):
    start_balance: float
    cash: float
    equity: float
    realized_pnl: float
    unrealized_pnl: float
    return_pct: float
    open_positions: int
    closed_positions: int
    wins: int
    losses: int
    win_rate: float | None
    avg_win_pct: float | None
    avg_loss_pct: float | None
    plan: list[str] = []
    disclaimer: str = (
        "Бумажная симуляция. Не инвест-рекомендация и НЕ прогноз прибыли. "
        "План ниже — что бот сделает по правилам, а не обещание результата."
    )


class PaperPositionList(BaseModel):
    items: list[PaperPositionOut]
    total: int


class NewsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    url: str
    title: str
    published_at: datetime | None
    catalyst: str | None
    sentiment: float | None
    urgency: str | None
    credibility: str | None
    model: str | None
    created_at: datetime


class NewsList(BaseModel):
    items: list[NewsOut]
    total: int


class ArticleCard(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    lang: str
    title: str
    meta_description: str
    source_name: str | None
    published_at: datetime


class ArticleOut(ArticleCard):
    keywords: str | None
    body: str
    source_url: str | None


class ArticleList(BaseModel):
    items: list[ArticleCard]
    total: int


class UserOut(BaseModel):
    id: int
    auth_method: str
    email: str | None
    display_name: str | None
    tier: str
    tier_expires_at: datetime | None
    is_admin: bool = False


class AuthToken(BaseModel):
    token: str
    user: UserOut


class NonceOut(BaseModel):
    address: str
    message: str


class TierInfo(BaseModel):
    id: str
    name: str
    price_usd: float
    features: list[str]


class CheckoutOut(BaseModel):
    invoice_url: str | None
    payment_id: int
    tier: str


class SafetyOut(BaseModel):
    token_id: int
    chain: str
    address: str
    risk_score: int
    verdict: str
    created_at: datetime
    sources: str | None
    flags: list = []
    is_malicious: bool = False

    @classmethod
    def from_report(cls, r) -> SafetyOut:
        try:
            flags = json.loads(r.red_flags) if r.red_flags else []
        except (ValueError, TypeError):
            flags = []
        return cls(
            token_id=r.token_id,
            chain=r.chain,
            address=r.address,
            risk_score=r.risk_score,
            verdict=r.verdict,
            created_at=r.created_at,
            sources=r.sources,
            flags=flags,
            is_malicious=is_malicious_flags(flags),
        )


class HealthOut(BaseModel):
    status: str
    version: str


# ---- per-user paper account ----
class UserPaperPositionOut(BaseModel):
    id: int
    symbol: str
    chain: str
    amount_usd: float
    value: float
    pnl_pct: float
    opened_at: datetime


class UserPaperTradeOut(BaseModel):
    symbol: str
    chain: str
    amount_usd: float
    exit_value: float
    pnl_usd: float
    pnl_pct: float
    closed_at: datetime


class UserPaperOut(BaseModel):
    opened: bool
    start_balance: float = 0.0
    cash: float = 0.0
    equity: float = 0.0
    pnl_pct: float | None = None
    win_rate: int | None = None
    positions: list[UserPaperPositionOut] = []
    trades: list[UserPaperTradeOut] = []


class OpenPaperIn(BaseModel):
    start_balance: float = 1000.0


# ---- simulated autotrade ----
class AutotradeConfigOut(BaseModel):
    enabled: bool
    max_position_usd: float
    daily_cap_usd: float
    min_confidence: float
    tp_pct: float
    stop_pct: float
    chains: str
    day_spent_usd: float
    last_run_at: datetime | None = None


class AutotradeConfigIn(BaseModel):
    enabled: bool | None = None
    max_position_usd: float | None = None
    daily_cap_usd: float | None = None
    min_confidence: float | None = None
    tp_pct: float | None = None
    stop_pct: float | None = None
    chains: str | None = None


class AutotradeRunOut(BaseModel):
    enabled: bool
    opened: int = 0
    closed: int = 0
    open_positions: int = 0
    day_spent_usd: float = 0.0
    equity: float = 0.0
    note: str = ""


class BuyPaperIn(BaseModel):
    symbol: str
    chain: str = ""
    amount_usd: float
