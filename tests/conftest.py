from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def make_alembic_config(database_url: str) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    return config


@pytest_asyncio.fixture()
async def session_factory(tmp_path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    db_path = tmp_path / "test.db"
    sync_url = f"sqlite:///{db_path}"
    async_url = f"sqlite+aiosqlite:///{db_path}"

    config = make_alembic_config(sync_url)
    command.upgrade(config, "head")

    engine = create_async_engine(async_url, future=True)

    async with engine.begin() as connection:
        await connection.execute(text("PRAGMA foreign_keys=ON"))

    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        yield session_maker
    finally:
        await engine.dispose()
