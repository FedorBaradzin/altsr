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
]


async def create_all() -> None:
    """Создать таблицы (для тестов и локального старта без Alembic)."""
    from . import models  # noqa: F401  регистрирует модели в метаданных

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if engine.dialect.name == "postgresql":
            from sqlalchemy import text

            for table, col, typ in _ENSURE_PG_COLUMNS:
                await conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {typ}")
                )


def reset_engine_for_tests() -> None:
    """Сбросить закэшированный движок (используется в тест-фикстурах)."""
    global _engine, _sessionmaker
    _engine = None
    _sessionmaker = None
