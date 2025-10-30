from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.types import Lifespan

from backend.core.config import Settings
from backend.db.session import dispose_engine, get_engine


def create_lifespan(settings: Settings) -> Lifespan[FastAPI]:
    logger = structlog.get_logger(__name__).bind(environment=settings.environment)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info("application_startup")
        # Initialise the database engine lazily so it can be reused across the app lifecycle.
        get_engine(settings)

        try:
            yield
        finally:
            await dispose_engine()
            logger.info("application_shutdown")

    return lifespan
