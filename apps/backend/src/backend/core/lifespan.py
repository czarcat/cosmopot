from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.types import Lifespan

from backend.auth.rate_limiter import RateLimiter
from backend.core.config import Settings
from backend.core.redis import close_redis, init_redis
from backend.db.session import dispose_engine, get_engine


def create_lifespan(settings: Settings) -> Lifespan[FastAPI]:
    logger = structlog.get_logger(__name__).bind(environment=settings.environment)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info("application_startup")
        # Initialise pooled resources so they can be reused across requests.
        get_engine(settings)
        redis = await init_redis(settings)
        app.state.redis = redis
        app.state.rate_limiter = RateLimiter(
            redis,
            limit=settings.rate_limit.requests_per_minute,
            window_seconds=settings.rate_limit.window_seconds,
        )

        try:
            yield
        finally:
            app.state.rate_limiter = None
            await close_redis()
            await dispose_engine()
            logger.info("application_shutdown")

    return lifespan
