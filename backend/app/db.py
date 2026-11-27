"""Async-слой БД (SQLAlchemy 2.x).

Движок создаётся лениво, чтобы тесты могли переопределить DATABASE_URL
до первого обращения. Поддерживаются postgres+asyncpg (прод) и
sqlite+aiosqlite (тесты).
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей."""


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        url = get_settings().database_url
        # sqlite в памяти требует StaticPool, иначе каждое соединение — новая БД.
        if url.startswith("sqlite"):
            from sqlalchemy.pool import StaticPool

            _engine = create_async_engine(
                url,
                echo=False,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        else:
            _engine = create_async_engine(url, echo=False, pool_pre_ping=True)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI-зависимость: сессия на запрос."""
    async with get_sessionmaker()() as session:
        yield session


# Колонки, добавленные к уже существующим таблицам. create_all() создаёт только
# НОВЫЕ таблицы и не добавляет колонки в существующие, а прод работает без Alembic —
# поэтому на старте идемпотентно досоздаём недостающие колонки (только PostgreSQL).
_ENSURE_PG_COLUMNS: list[tuple[str, str, str]] = [
    ("user_paper_positions", "entry_price", "DOUBLE PRECISION"),
    ("user_paper_positions", "address", "VARCHAR(128)"),
    ("user_paper_positions", "pair_address", "VARCHAR(128)"),
    ("users", "tg_chat_id", "VARCHAR(32)"),
    ("tokens", "price_usd", "DOUBLE PRECISION"),
    ("tokens", "first_price_usd", "DOUBLE PRECISION"),
    ("tokens", "first_liquidity_usd", "DOUBLE PRECISION"),
    ("tokens", "price_change_h24", "DOUBLE PRECISION"),
    ("tokens", "price_change_h1", "DOUBLE PRECISION"),
    ("tokens", "price_change_h6", "DOUBLE PRECISION"),
    ("tokens", "volume_h24", "DOUBLE PRECISION"),
    ("tokens", "txns_h24", "INTEGER"),
    ("tokens", "market_cap_usd", "DOUBLE PRECISION"),
    ("tokens", "image_url", "VARCHAR(512)"),
    ("tokens", "smart_wallets", "INTEGER NOT NULL DEFAULT 0"),
    ("paper_positions", "tp_tiers_hit", "INTEGER NOT NULL DEFAULT 0"),
    # Реферальная программа: новые колонки существующей таблицы users.
    ("users", "referral_code", "VARCHAR(16)"),
    ("users", "referred_by_id", "INTEGER"),
    ("users", "referral_rate_override", "DOUBLE PRECISION"),
]


async def create_all() -> None:
    """Создать таблицы (для тестов и локального старта без Alembic)."""
    from . import models  # noqa: F401  регистрирует модели в метаданных
    from sqlalchemy.exc import ProgrammingError

    engine = get_engine()
    # Несколько сервисов (backend/worker/paper/signals/ai) выполняют create_all
    # одновременно на старте. Даже с checkfirst две параллельные попытки могут
    # столкнуться на CREATE TABLE ("relation ... already exists") и уронить
    # startup. Таблицы при этом уже созданы — глотаем именно эту гонку.
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except ProgrammingError as exc:  # pragma: no cover - зависит от гонки на старте
        if "already exists" not in str(exc).lower():
            raise

    if engine.dialect.name == "postgresql":
        from sqlalchemy import text

        # Идемпотентное добавление новых колонок в существующие таблицы
        # (create_all создаёт только новые ТАБЛИЦЫ, но не колонки). Отдельная
        # транзакция, чтобы не зависеть от исхода блока выше.
        async with engine.begin() as conn:
            for table, col, typ in _ENSURE_PG_COLUMNS:
                await conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {typ}")
                )


def reset_engine_for_tests() -> None:
    """Сбросить закэшированный движок (используется в тест-фикстурах)."""
    global _engine, _sessionmaker
    _engine = None
    _sessionmaker = None
