from __future__ import annotations

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends

from backend.core.config import Settings, get_settings

router = APIRouter(prefix="/health", tags=["health"])
logger = structlog.get_logger(__name__)


@router.get("", summary="Service health check")
async def health(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    """Return a lightweight health payload for readiness probes."""

    payload = {
        "status": "ok",
        "service": settings.project_name,
        "version": settings.project_version,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    logger.debug("health_status", **payload)
    return payload
