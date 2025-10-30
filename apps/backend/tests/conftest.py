from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient

import backend.auth.models  # noqa: F401 - ensure models are registered with SQLAlchemy
from backend.app import create_app
from backend.core.config import get_settings
feat/auth-web-jwt-refresh-rotation-revocation-redis-rate-limit-argon2-tests
from backend.db.base import Base
from backend.db.session import dispose_engine, get_engine

from backend.db.session import dispose_engine, get_engine
from user_service.models import Base as UserBase

TEST_BOT_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
TEST_JWT_SECRET = "test-jwt-secret-key"
main


@pytest.fixture(scope="session")
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


@pytest_asyncio.fixture(autouse=True)
async def configure_environment(tmp_path, monkeypatch) -> AsyncIterator[None]:
    db_path = tmp_path / "backend-test.db"
    database_url = f"sqlite+aiosqlite:///{db_path}"

    monkeypatch.setenv("DATABASE__URL", database_url)
    monkeypatch.setenv("TELEGRAM__BOT_TOKEN", TEST_BOT_TOKEN)
    monkeypatch.setenv("TELEGRAM__LOGIN_TTL_SECONDS", "86400")
    monkeypatch.setenv("JWT__SECRET_KEY", TEST_JWT_SECRET)
    monkeypatch.setenv("JWT__ALGORITHM", "HS256")
    monkeypatch.setenv("JWT__ACCESS_TTL_SECONDS", "3600")

    get_settings.cache_clear()
    settings = get_settings()

    engine = get_engine(settings)
    async with engine.begin() as connection:
        await connection.run_sync(UserBase.metadata.create_all)

    try:
        yield
    finally:
        await dispose_engine()
        get_settings.cache_clear()


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
