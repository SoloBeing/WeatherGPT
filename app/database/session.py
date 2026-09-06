"""
Database Session — Async SQLAlchemy 2.0 engine and session factory.

Manages connection pooling for PostgreSQL with PostGIS (alert polygons,
gazetteer spatial indexing) and TimescaleDB (station timeseries hypertables).
"""

from collections.abc import AsyncGenerator
import logging
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql import text

from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy ORM models."""
    pass


# Global engine and session factory instances
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Get or create the singleton async SQLAlchemy engine."""
    global _engine
    if _engine is None:
        db_url = settings.DATABASE_URL
        connect_args: dict[str, Any] = {}
        if db_url.startswith("sqlite"):
            connect_args = {"check_same_thread": False}

        engine_kwargs: dict[str, Any] = {
            "echo": settings.DEBUG,
            "pool_pre_ping": True,
            "connect_args": connect_args,
        }
        if not db_url.startswith("sqlite"):
            engine_kwargs.update(
                {
                    "pool_size": settings.DB_POOL_SIZE,
                    "max_overflow": settings.DB_MAX_OVERFLOW,
                    "pool_timeout": settings.DB_POOL_TIMEOUT,
                    "pool_recycle": settings.DB_POOL_RECYCLE,
                }
            )

        _engine = create_async_engine(db_url, **engine_kwargs)
        logger.info(
            "Async database engine created (pool_size=%s, max_overflow=%s, recycle=%ss)",
            getattr(_engine.pool, "_pool", None) and getattr(_engine.pool, "size", lambda: None)() or settings.DB_POOL_SIZE,
            settings.DB_MAX_OVERFLOW,
            settings.DB_POOL_RECYCLE,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the singleton async sessionmaker."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency yielding an async database session.
    Closes and rolls back on exception automatically.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_db_health() -> bool:
    """
    Ping the database with a lightweight SELECT 1 query.
    Returns True if healthy, False if unreachable.
    """
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning(f"Database health check failed: {exc}")
        return False


async def close_db() -> None:
    """Dispose of the database engine pool on application shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database connection pool disposed.")

