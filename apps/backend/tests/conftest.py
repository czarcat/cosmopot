from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import backend.auth.models  # noqa: F401 - ensure models registered with SQLAlchemy metadata
import backend.payments.models  # noqa: F401 - ensure models registered with SQLAlchemy metadata
from backend.app import create_app
from backend.core.config import get_settings
from backend.db import session as db_session
from backend.db.base import Base
from backend.db.dependencies import get_db_session
from backend.db.session import dispose_engine
from backend.payments.dependencies import reset_payment_dependencies
from user_service.models import Base as UserBase

TEST_JWT_SECRET = "test-jwt-secret-key"
TEST_BOT_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"


@pytest.fixture(scope="session")
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


@pytest.fixture(autouse=True)
def configure_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("DATABASE__URL", "postgresql+asyncpg://test:test@localhost/test")
    monkeypatch.setenv("REDIS__URL", "fakeredis://")
    monkeypatch.setenv("JWT__SECRET_KEY", TEST_JWT_SECRET)
    monkeypatch.setenv("JWT__ALGORITHM", "HS256")
    monkeypatch.setenv("JWT__ACCESS_TTL_SECONDS", "3600")
    monkeypatch.setenv("TELEGRAM__BOT_TOKEN", TEST_BOT_TOKEN)
    monkeypatch.setenv("S3__BUCKET", "test-generation")
    monkeypatch.setenv("S3__REGION", "us-east-1")
    monkeypatch.setenv("S3__ACCESS_KEY_ID", "test-access")
    monkeypatch.setenv("S3__SECRET_ACCESS_KEY", "test-secret")
    monkeypatch.setenv("RABBITMQ__URL", "amqp://guest:guest@localhost:5672/")

    reset_payment_dependencies()
    get_settings.cache_clear()
    try:
        yield
    finally:
        reset_payment_dependencies()
        get_settings.cache_clear()


@pytest_asyncio.fixture()
async def session_factory(tmp_path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    db_path = tmp_path / "backend-tests.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(UserBase.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    db_session._ENGINE = engine
    db_session._SESSION_FACTORY = factory

    try:
        yield factory
    finally:
        await dispose_engine()


@pytest_asyncio.fixture()
async def app(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[FastAPI]:
    application = create_app()

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
            finally:
                transaction = session.get_transaction()
                if transaction is not None and transaction.is_active:
                    await session.rollback()

    application.dependency_overrides[get_db_session] = override_get_db_session

    try:
        yield application
    finally:
        application.dependency_overrides.clear()


@pytest_asyncio.fixture()
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
