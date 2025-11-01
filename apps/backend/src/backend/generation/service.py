from __future__ import annotations

from collections.abc import Callable

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Awaitable
from uuid import UUID

import aio_pika
import structlog

try:  # pragma: no cover - boto3 fallback for environments without aioboto3
    import aioboto3  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    aioboto3 = None  # type: ignore[assignment]
    import boto3
else:  # pragma: no cover
    boto3 = None  # type: ignore[assignment]

from backend.core.config import Settings

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class S3UploadResult:
    key: str
    url: str


class S3Storage:
    """Lightweight wrapper around S3-compatible storage for original assets."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._access_key = (
            settings.s3.access_key_id.get_secret_value()
            if settings.s3.access_key_id
            else None
        )
        self._secret_key = (
            settings.s3.secret_access_key.get_secret_value()
            if settings.s3.secret_access_key
            else None
        )
        if aioboto3 is not None:
            self._session = aioboto3.Session(  # type: ignore[call-arg]
                aws_access_key_id=self._access_key,
                aws_secret_access_key=self._secret_key,
                region_name=settings.s3.region,
            )
        else:  # pragma: no cover - boto3 synchronous fallback
            self._session = None

    def _client_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "aws_access_key_id": self._access_key,
            "aws_secret_access_key": self._secret_key,
            "region_name": self._settings.s3.region,
        }
        if self._settings.s3.endpoint_url:
            kwargs["endpoint_url"] = self._settings.s3.endpoint_url
        return kwargs

    async def upload_original(
        self,
        *,
        user_id: int,
        task_id: UUID,
        content: bytes,
        content_type: str,
        extension: str,
    ) -> S3UploadResult:
        key = f"input/{user_id}/{task_id}{extension}"

        if aioboto3 is not None and self._session is not None:
            client_kwargs = self._client_kwargs()
            async with self._session.client("s3", **client_kwargs) as client:
                await client.put_object(
                    Bucket=self._settings.s3.bucket,
                    Key=key,
                    Body=content,
                    ContentType=content_type,
                    ACL="private",
                )
                url = client.generate_presigned_url(  # type: ignore[no-untyped-call]
                    "get_object",
                    Params={"Bucket": self._settings.s3.bucket, "Key": key},
                    ExpiresIn=self._settings.s3.presign_ttl_seconds,
                )
        else:  # pragma: no cover - boto3 synchronous fallback
            assert boto3 is not None  # for type checkers
            client = boto3.client("s3", **self._client_kwargs())
            await asyncio.to_thread(
                client.put_object,
                Bucket=self._settings.s3.bucket,
                Key=key,
                Body=content,
                ContentType=content_type,
                ACL="private",
            )
            url = client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._settings.s3.bucket, "Key": key},
                ExpiresIn=self._settings.s3.presign_ttl_seconds,
            )

        logger.info(
            "generation_original_uploaded", key=key, bucket=self._settings.s3.bucket
        )
        return S3UploadResult(key=key, url=url)


class QueuePublisher:
    """RabbitMQ publisher ensuring tasks are enqueued with priority semantics."""

    def __init__(
        self,
        settings: Settings,
        connection_factory: (
            Callable[[str], Awaitable[aio_pika.RobustConnection]] | None
        ) = None,
    ) -> None:
        self._settings = settings
        self._connection_factory = connection_factory

    async def _connect(self) -> aio_pika.RobustConnection:
        if self._connection_factory is not None:
            return await self._connection_factory(self._settings.rabbitmq.url)
        return await aio_pika.connect_robust(self._settings.rabbitmq.url)

    async def publish(self, payload: dict[str, Any], *, priority: int) -> None:
        connection = await self._connect()
        try:
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=1)

            exchange = await channel.declare_exchange(
                self._settings.rabbitmq.exchange,
                aio_pika.ExchangeType.DIRECT,
                durable=True,
            )
            queue = await channel.declare_queue(
                self._settings.rabbitmq.queue,
                durable=True,
                arguments={"x-max-priority": self._settings.rabbitmq.max_priority},
            )
            await queue.bind(exchange, routing_key=self._settings.rabbitmq.routing_key)

            message = aio_pika.Message(
                body=json.dumps(payload).encode("utf-8"),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                priority=min(priority, self._settings.rabbitmq.max_priority),
            )
            await exchange.publish(
                message, routing_key=self._settings.rabbitmq.routing_key
            )
            logger.info(
                "generation_task_enqueued",
                routing_key=self._settings.rabbitmq.routing_key,
                queue=self._settings.rabbitmq.queue,
                priority=priority,
            )
        finally:
            await connection.close()


class GenerationService:
    """Facilitates storage and queue side-effects for generation submissions."""

    def __init__(
        self,
        settings: Settings,
        *,
        storage: S3Storage | None = None,
        publisher: QueuePublisher | None = None,
    ) -> None:
        self._settings = settings
        self._storage = storage or S3Storage(settings)
        self._publisher = publisher or QueuePublisher(settings)

    async def store_original(
        self,
        *,
        user_id: int,
        task_id: UUID,
        content: bytes,
        content_type: str,
        extension: str,
    ) -> S3UploadResult:
        return await self._storage.upload_original(
            user_id=user_id,
            task_id=task_id,
            content=content,
            content_type=content_type,
            extension=extension,
        )

    async def enqueue(self, payload: dict[str, Any], *, priority: int) -> None:
        await self._publisher.publish(payload, priority=priority)


def resolve_priority(level: str | None) -> int:
    """Map subscription tiers to RabbitMQ priority values."""

    mapping = {
        "basic": 3,
        "standard": 5,
        "premium": 9,
        "pro": 9,
        "enterprise": 9,
        "free": 1,
    }
    if level is None:
        return mapping["basic"]
    normalised = level.strip().lower()
    return mapping.get(normalised, mapping["basic"])
