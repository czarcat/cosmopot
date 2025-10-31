from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    """Create an async engine for the given database URL."""

    return create_async_engine(url, echo=echo, future=True)


def create_session_factory(
    engine: AsyncEngine, *, expire_on_commit: bool = False
) -> async_sessionmaker[AsyncSession]:
    """Return an async session factory bound to the provided engine."""

    return async_sessionmaker(engine, expire_on_commit=expire_on_commit)


@asynccontextmanager
async def session_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Simple async context manager yielding a session and guaranteeing cleanup."""

    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
