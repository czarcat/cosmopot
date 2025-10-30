from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

import backend.auth.models  # noqa: F401 - ensure models are registered with SQLAlchemy
from backend.app import create_app
from backend.core.config import get_settings
from backend.db.base import Base
from backend.db.session import dispose_engine, get_engine


@pytest.fixture(scope="session")
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


@pytest.fixture()
def configure_settings(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Iterator[None]:
    db_path = tmp_path / "backend-test.db"
    monkeypatch.setenv("DATABASE__URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("REDIS__URL", "fakeredis://")
    monkeypatch.setenv("JWT__SECRET", "test-secret-key")
    monkeypatch.setenv("RATE_LIMIT__REQUESTS_PER_MINUTE", "5")

    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


@pytest.fixture()
async def app(configure_settings: None) -> AsyncIterator[FastAPI]:
    application = create_app()
    settings = application.state.settings

    engine = get_engine(settings)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        yield application
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await dispose_engine()


@pytest.fixture()
async def async_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        redis = getattr(app.state, "redis", None)
        if redis is not None:
            await redis.flushdb()
        try:
            yield client
        finally:
            if redis is not None:
                await redis.flushdb()
