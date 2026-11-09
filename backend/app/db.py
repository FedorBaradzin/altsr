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


async def create_all() -> None:
    """Создать таблицы (для тестов и локального старта без Alembic)."""
    from . import models  # noqa: F401  регистрирует модели в метаданных

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def reset_engine_for_tests() -> None:
    """Сбросить закэшированный движок (используется в тест-фикстурах)."""
    global _engine, _sessionmaker
    _engine = None
    _sessionmaker = None
