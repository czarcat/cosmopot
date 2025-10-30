from __future__ import annotations

from urllib.parse import urlparse

from redis.asyncio import Redis

from backend.core.config import Settings, get_settings

try:  # pragma: no cover - optional dependency in production
    from fakeredis.aioredis import FakeRedis  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fakeredis is only needed for tests
    FakeRedis = None


_REDIS: Redis | None = None


async def init_redis(settings: Settings | None = None) -> Redis:
    """Initialise and cache the Redis client."""

    global _REDIS
    if _REDIS is not None:
        return _REDIS

    settings = settings or get_settings()
    url = settings.redis.url
    parsed = urlparse(url)

    if parsed.scheme in {"fakeredis", "memory"} and FakeRedis is not None:
        _REDIS = FakeRedis()
    else:
        _REDIS = Redis.from_url(url, encoding="utf-8", decode_responses=True)

    await _REDIS.ping()
    return _REDIS


async def get_redis(settings: Settings | None = None) -> Redis:
    return await init_redis(settings)


async def close_redis() -> None:
    global _REDIS
    if _REDIS is None:
        return

    close = getattr(_REDIS, "aclose", None)
    if callable(close):  # pragma: no branch - mypy friendly
        await close()
    else:  # pragma: no cover - fallback for legacy clients
        await _REDIS.close()
    _REDIS = None
