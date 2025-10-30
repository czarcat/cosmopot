from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app import create_app
p0-feat-user-api-profile-rbac-sessions-balance-tests-openapi
from backend.db.dependencies import get_db_session
from user_service.models import Base

from backend.core.config import get_settings
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


p0-feat-user-api-profile-rbac-sessions-balance-tests-openapi
@pytest_asyncio.fixture()
async def session_factory(tmp_path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    db_path = tmp_path / "api-tests.db"
    async_engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)

    async with async_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(async_engine, expire_on_commit=False, autoflush=False)

    try:
        yield factory
    finally:
        await async_engine.dispose()


@pytest_asyncio.fixture()
async def app(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[FastAPI]:
=======
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
async def app() -> AsyncIterator[FastAPI]:
main
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
        yield client
