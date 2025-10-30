from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient

from backend.app import create_app
from backend.core.config import get_settings
from backend.db.session import dispose_engine, get_engine
from user_service.models import Base as UserBase

TEST_BOT_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
TEST_JWT_SECRET = "test-jwt-secret-key"


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
async def app() -> AsyncIterator[FastAPI]:
    application = create_app()
    yield application


@pytest.fixture()
async def async_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        yield client
