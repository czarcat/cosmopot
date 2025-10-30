from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError

try:  # pragma: no cover - fallback when prometheus_client is unavailable
    from prometheus_client import Counter
except ModuleNotFoundError:  # pragma: no cover
    class Counter:  # type: ignore[override]
        def __init__(self, *args, **kwargs) -> None:
            pass

        def labels(self, **kwargs):  # type: ignore[override]
            return self

        def inc(self, amount: float = 1.0) -> None:  # type: ignore[override]
            return None

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies.users import get_current_user
from backend.api.schemas.generation import (
    GenerationParameters,
    GenerationTaskEnvelope,
    GenerationTaskStatusResponse,
)
from backend.core.config import Settings, get_settings
from backend.db.dependencies import get_db_session
from backend.generation.enums import GenerationEventType, GenerationTaskStatus
from backend.generation.repository import add_event, create_task, get_task_by_id
from backend.generation.service import GenerationService, resolve_priority
from user_service.enums import SubscriptionStatus
from user_service.models import Subscription, User

router = APIRouter(prefix="/api/v1", tags=["generation"])
logger = structlog.get_logger(__name__)

_ALLOWS: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
}
_MAX_IMAGE_BYTES = 8 * 1024 * 1024

_GENERATION_REQUESTS = Counter(
    "generation_requests_total",
    "Total generation requests processed by the API",
    labelnames=("outcome",),
)
_GENERATION_ENQUEUED = Counter(
    "generation_tasks_enqueued_total",
    "Total generation tasks successfully enqueued",
)


def get_generation_service(settings: Settings = Depends(get_settings)) -> GenerationService:
    return GenerationService(settings)


async def _get_active_subscription(session: AsyncSession, user_id: int) -> Subscription | None:
    stmt = (
        select(Subscription)
        .where(
            Subscription.user_id == user_id,
            Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]),
        )
        .order_by(Subscription.current_period_end.desc())
        .limit(1)
        .with_for_update()
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _parse_parameters(raw: str | None) -> GenerationParameters:
    if raw is None or not raw.strip():
        return GenerationParameters()
    try:
        return GenerationParameters.model_validate_json(raw)
    except ValidationError as exc:  # pragma: no cover - converted to HTTP error
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid parameters payload") from exc


def _normalise_prompt(prompt: str) -> str:
    cleaned = prompt.strip()
    if not cleaned:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Prompt must not be empty")
    return cleaned


def _content_type_extension(upload: UploadFile) -> tuple[str, str]:
    content_type = (upload.content_type or "").lower()
    if content_type not in _ALLOWS:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported image type")
    return content_type, _ALLOWS[content_type]


@router.post(
    "/generate",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=GenerationTaskEnvelope,
    summary="Submit an image generation job",
)
async def submit_generation_task(
    prompt: str = Form(..., description="Text prompt guiding the generation"),
    parameters_raw: str | None = Form(
        None,
        description="Optional JSON encoded parameter overrides",
        alias="parameters",
    ),
    file: UploadFile = File(..., description="Input image seed"),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    service: GenerationService = Depends(get_generation_service),
) -> GenerationTaskEnvelope:
    prompt_value = _normalise_prompt(prompt)
    try:
        parameters = _parse_parameters(parameters_raw)
    except HTTPException:
        _GENERATION_REQUESTS.labels(outcome="invalid_parameters").inc()
        raise

    content = await file.read()
    if not content:
        _GENERATION_REQUESTS.labels(outcome="invalid_image").inc()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Image file is required")
    if len(content) > _MAX_IMAGE_BYTES:
        _GENERATION_REQUESTS.labels(outcome="too_large").inc()
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Image exceeds size limit")

    try:
        content_type, extension = _content_type_extension(file)
    except HTTPException:
        _GENERATION_REQUESTS.labels(outcome="unsupported_type").inc()
        raise

    subscription = await _get_active_subscription(session, current_user.id)
    if subscription is None:
        _GENERATION_REQUESTS.labels(outcome="no_subscription").inc()
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Active subscription required")

    if subscription.quota_limit and subscription.quota_used >= subscription.quota_limit:
        _GENERATION_REQUESTS.labels(outcome="quota_exhausted").inc()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Generation quota exhausted")

    subscription.quota_used += 1

    task_id = uuid.uuid4()
    priority = resolve_priority(subscription.tier.value if subscription.tier else None)
    tier_label = subscription.tier.value if subscription.tier else "basic"

    metadata: dict[str, Any] = {
        "filename": file.filename,
        "content_type": content_type,
    }

    try:
        upload_result = await service.store_original(
            user_id=current_user.id,
            task_id=task_id,
            content=content,
            content_type=content_type,
            extension=extension,
        )

        task = await create_task(
            session,
            user_id=current_user.id,
            prompt=prompt_value,
            parameters=parameters.model_dump(),
            status=GenerationTaskStatus.QUEUED,
            priority=priority,
            subscription_tier=tier_label,
            s3_bucket=settings.s3.bucket,
            s3_key=upload_result.key,
            input_url=upload_result.url,
            metadata=metadata,
            task_id=task_id,
        )

        await add_event(
            session,
            task=task,
            event_type=GenerationEventType.CREATED,
            message="Generation task created",
            data={"priority": priority, "subscription_tier": tier_label},
        )
        await add_event(
            session,
            task=task,
            event_type=GenerationEventType.STORAGE_UPLOADED,
            message="Original asset stored",
            data={"key": upload_result.key, "bucket": settings.s3.bucket},
        )

        message_payload = {
            "task_id": str(task.id),
            "user_id": current_user.id,
            "prompt": prompt_value,
            "parameters": parameters.model_dump(),
            "input_url": upload_result.url,
            "s3_bucket": settings.s3.bucket,
            "s3_key": upload_result.key,
            "priority": priority,
            "subscription_tier": tier_label,
        }
        await service.enqueue(message_payload, priority=priority)
        await add_event(
            session,
            task=task,
            event_type=GenerationEventType.QUEUE_PUBLISHED,
            message="Task enqueued for processing",
            data=message_payload,
        )

        await session.commit()
    except HTTPException:
        await session.rollback()
        raise
    except Exception as exc:  # pragma: no cover - defensive logging
        await session.rollback()
        logger.exception(
            "generation_submission_failed",
            user_id=current_user.id,
            task_id=str(task_id),
            error=str(exc),
        )
        _GENERATION_REQUESTS.labels(outcome="error").inc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to enqueue generation task") from exc

    _GENERATION_REQUESTS.labels(outcome="success").inc()
    _GENERATION_ENQUEUED.inc()
    logger.info(
        "generation_task_submitted",
        user_id=current_user.id,
        task_id=str(task.id),
        priority=priority,
        tier=tier_label,
    )
    return GenerationTaskEnvelope.model_validate(task)


@router.get(
    "/tasks/{task_id}/status",
    response_model=GenerationTaskStatusResponse,
    summary="Retrieve the latest status for a generation task",
)
async def get_generation_status(
    task_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> GenerationTaskStatusResponse:
    task = await get_task_by_id(session, task_id)
    if task is None or task.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return GenerationTaskStatusResponse.model_validate(task)
