"""ORM-модели.

Фаза 0 — только таблица tokens (единая нормализованная модель токена).
Таблицы safety_reports / signals / paper_* добавятся в следующих фазах;
модель tokens спроектирована под внешние ключи от них.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Token(Base):
    """Нормализованный токен/пара из любого источника discovery."""

    __tablename__ = "tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Единая модель (п.4 промта): chain, address, symbol, name, created_at,
    # liquidity_usd, fdv, pair_address, dex, socials.
    chain: Mapped[str] = mapped_column(String(32), nullable=False)
    address: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str | None] = mapped_column(String(256))

    # Время создания токена/пары в сети (из источника).
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    liquidity_usd: Mapped[float | None] = mapped_column(Float)
    fdv: Mapped[float | None] = mapped_column(Float)
    pair_address: Mapped[str | None] = mapped_column(String(128))
    dex: Mapped[str | None] = mapped_column(String(64))
    # socials/links как JSON-строка (websites, twitter, telegram, explorer).
    socials: Mapped[str | None] = mapped_column(String(2048))

    source: Mapped[str] = mapped_column(String(32), nullable=False)
    # Монотонный ключ для WS-курсора «что нового».
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    seen_count: Mapped[int] = mapped_column(BigInteger, default=1, nullable=False)

    __table_args__ = (
        # Дедуп на уровне БД: один токен на (chain, address).
        UniqueConstraint("chain", "address", name="uq_tokens_chain_address"),
        Index("ix_tokens_chain_address", "chain", "address"),
        Index("ix_tokens_discovered_at", "discovered_at"),
        Index("ix_tokens_chain", "chain"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Token {self.chain}:{self.address} {self.symbol!r}>"


class SafetyReport(Base):
    """Результат анти-скам скрининга токена (Фаза 1).

    Храним последний отчёт на токен (uq по token_id) + историю через created_at,
    если понадобится ресканирование. verdict ∈ {PASS, REVIEW, BLOCK}.
    """

    __tablename__ = "safety_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_id: Mapped[int] = mapped_column(
        ForeignKey("tokens.id", ondelete="CASCADE"), nullable=False
    )
    chain: Mapped[str] = mapped_column(String(32), nullable=False)
    address: Mapped[str] = mapped_column(String(128), nullable=False)

    # 0–100, выше = рискованнее.
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    verdict: Mapped[str] = mapped_column(String(8), nullable=False)
    # red_flags[] и raw-ответы провайдеров — JSON-строками.
    red_flags: Mapped[str | None] = mapped_column(Text)
    findings: Mapped[str | None] = mapped_column(Text)
    sources: Mapped[str | None] = mapped_column(String(256))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("token_id", name="uq_safety_token"),
        Index("ix_safety_token_id", "token_id"),
        Index("ix_safety_verdict", "verdict"),
        Index("ix_safety_chain_address", "chain", "address"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SafetyReport {self.chain}:{self.address} {self.verdict} {self.risk_score}>"


class Signal(Base):
    """BUY-сигнал движка входа (Фаза 2). Один активный сигнал на токен."""

    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_id: Mapped[int] = mapped_column(
        ForeignKey("tokens.id", ondelete="CASCADE"), nullable=False
    )
    chain: Mapped[str] = mapped_column(String(32), nullable=False)
    address: Mapped[str] = mapped_column(String(128), nullable=False)

    side: Mapped[str] = mapped_column(String(8), default="BUY", nullable=False)
    # Уверенность 0..1.
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    # reasons[] — почему прошёл; JSON-строкой.
    reasons: Mapped[str | None] = mapped_column(Text)
    # venues/как купить — JSON-строкой (снимок на момент сигнала).
    venues: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="new", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("token_id", name="uq_signal_token"),
        Index("ix_signal_token_id", "token_id"),
        Index("ix_signal_created_at", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Signal {self.side} {self.chain}:{self.address} c={self.confidence:.2f}>"


class PaperAccount(Base):
    """Единый бумажный счёт (singleton, id=1). Реальных денег нет."""

    __tablename__ = "paper_account"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    start_balance: Mapped[float] = mapped_column(Float, nullable=False)
    cash: Mapped[float] = mapped_column(Float, nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class PaperPosition(Base):
    """Бумажная позиция по токену. Частичные выходы через remaining_fraction."""

    __tablename__ = "paper_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_id: Mapped[int] = mapped_column(
        ForeignKey("tokens.id", ondelete="CASCADE"), nullable=False
    )
    chain: Mapped[str] = mapped_column(String(32), nullable=False)
    address: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(64))

    status: Mapped[str] = mapped_column(String(8), default="open", nullable=False)
    size_usd: Mapped[float] = mapped_column(Float, nullable=False)   # первоначальная ставка
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    peak_price: Mapped[float] = mapped_column(Float, nullable=False)
    last_price: Mapped[float] = mapped_column(Float, nullable=False)
    remaining_fraction: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    tp_taken: Mapped[bool] = mapped_column(default=False, nullable=False)

    realized_pnl_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    pnl_pct: Mapped[float | None] = mapped_column(Float)
    exit_reason: Mapped[str | None] = mapped_column(String(64))

    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    last_high_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("token_id", name="uq_paper_position_token"),
        Index("ix_paper_positions_status", "status"),
        Index("ix_paper_positions_token_id", "token_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PaperPosition {self.chain}:{self.address} {self.status}>"


class NewsItem(Base):
    """Новость/пост + ИИ-классификация (Фаза 4). Дедуп по url."""

    __tablename__ = "news_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Привязка к токену, если распознана.
    chain: Mapped[str | None] = mapped_column(String(32))
    address: Mapped[str | None] = mapped_column(String(128))

    # ИИ-классификация.
    classified: Mapped[bool] = mapped_column(default=False, nullable=False)
    catalyst: Mapped[str | None] = mapped_column(String(32))
    sentiment: Mapped[float | None] = mapped_column(Float)       # −1..+1
    urgency: Mapped[str | None] = mapped_column(String(8))       # low/med/high
    credibility: Mapped[str | None] = mapped_column(String(24))
    model: Mapped[str | None] = mapped_column(String(48))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("url", name="uq_news_url"),
        Index("ix_news_created_at", "created_at"),
        Index("ix_news_urgency", "urgency"),
        Index("ix_news_chain_address", "chain", "address"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<NewsItem {self.source} {self.catalyst} {self.urgency}>"


class Article(Base):
    """SEO-статья (оригинальный разбор на основе новости). Дедуп по slug."""

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(220), nullable=False)
    lang: Mapped[str] = mapped_column(String(5), default="en", nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    meta_description: Mapped[str] = mapped_column(String(320), nullable=False)
    keywords: Mapped[str | None] = mapped_column(String(400))
    body: Mapped[str] = mapped_column(Text, nullable=False)  # markdown, оригинальный текст

    source_url: Mapped[str | None] = mapped_column(String(1024))
    source_name: Mapped[str | None] = mapped_column(String(120))
    news_id: Mapped[int | None] = mapped_column(
        ForeignKey("news_items.id", ondelete="SET NULL")
    )
    model: Mapped[str | None] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(10), default="published", nullable=False)
    social_posted: Mapped[bool] = mapped_column(default=False, nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("slug", name="uq_article_slug"),
        Index("ix_article_published_at", "published_at"),
        Index("ix_article_news_id", "news_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Article {self.slug!r} {self.lang}>"


class User(Base):
    """Пользователь. Вход: wallet / google / telegram. tier — текущий тариф."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    auth_method: Mapped[str] = mapped_column(String(16), nullable=False)  # wallet/google/telegram
    # addr / google sub / telegram id
    subject: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str | None] = mapped_column(String(256))
    display_name: Mapped[str | None] = mapped_column(String(128))

    tier: Mapped[str] = mapped_column(String(16), default="free", nullable=False)
    tier_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Привязанный Telegram-чат пользователя (для личных алертов). NULL = не привязан.
    tg_chat_id: Mapped[str | None] = mapped_column(String(32))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    last_login_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("auth_method", "subject", name="uq_user_identity"),
        Index("ix_users_auth_subject", "auth_method", "subject"),
    )


class TelegramLinkCode(Base):
    """Одноразовый код привязки Telegram (deep-link /start=<code>). TTL проверяется по created_at."""

    __tablename__ = "telegram_link_codes"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.auth_method}:{self.subject} {self.tier}>"


class Payment(Base):
    """Платёж NOWPayments за тариф."""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    tier: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str] = mapped_column(String(24), default="nowpayments", nullable=False)
    invoice_id: Mapped[str | None] = mapped_column(String(64))
    payment_id: Mapped[str | None] = mapped_column(String(64))
    amount_usd: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="waiting", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_payments_user_id", "user_id"),
        Index("ix_payments_invoice", "invoice_id"),
        Index("ix_payments_payment_id", "payment_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Payment {self.tier} {self.status}>"


class SignalOutcome(Base):
    """Исход сигнала для обучения confidence (T3). Фичи на момент сигнала + метка.

    label: 1 — вырос за горизонт (win), 0 — упал/не вырос (loss), NULL — не resolved.
    features — JSON-строкой (порядок из calibration.FEATURE_NAMES).
    """

    __tablename__ = "signal_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chain: Mapped[str] = mapped_column(String(32), nullable=False)
    address: Mapped[str] = mapped_column(String(128), nullable=False)
    features: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    entry_price: Mapped[float | None] = mapped_column(Float)
    horizon_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[int | None] = mapped_column(Integer)  # NULL пока не resolved

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_signal_outcomes_chain_addr", "chain", "address"),
        Index("ix_signal_outcomes_label", "label"),
        Index("ix_signal_outcomes_created_at", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SignalOutcome {self.chain}:{self.address} label={self.label}>"


class UserPaperAccount(Base):
    """Персональный бумажный счёт пользователя (с нуля). Реальных денег нет."""

    __tablename__ = "user_paper_account"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    start_balance: Mapped[float] = mapped_column(Float, nullable=False)
    cash: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_paper_account_user"),
    )


class UserPaperPosition(Base):
    """Открытая бумажная позиция пользователя. Стоимость считается детерминированно."""

    __tablename__ = "user_paper_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("user_paper_account.id", ondelete="CASCADE"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    chain: Mapped[str] = mapped_column(String(32), nullable=False)
    amount_usd: Mapped[float] = mapped_column(Float, nullable=False)
    bias: Mapped[float] = mapped_column(Float, nullable=False)
    seed: Mapped[float] = mapped_column(Float, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_user_paper_positions_account", "account_id"),
    )


class UserPaperTrade(Base):
    """Закрытая бумажная сделка пользователя (история для Журнала)."""

    __tablename__ = "user_paper_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("user_paper_account.id", ondelete="CASCADE"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    chain: Mapped[str] = mapped_column(String(32), nullable=False)
    amount_usd: Mapped[float] = mapped_column(Float, nullable=False)
    exit_value: Mapped[float] = mapped_column(Float, nullable=False)
    pnl_usd: Mapped[float] = mapped_column(Float, nullable=False)
    pnl_pct: Mapped[float] = mapped_column(Float, nullable=False)
    closed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_user_paper_trades_account", "account_id"),
    )
