from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from typing import Any, Dict, List

import pytest
from backend.app.celery_app import celery_app
from backend.app.tasks import process_generation_task
from backend.app.worker import bootstrap
from backend.app.worker.banana import GeminiResult
from backend.app.worker.config import RuntimeOverrides, WorkerSettings
from backend.app.worker.storage import InMemoryStorage
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from tests.factories import (
    generation_task_create_factory,
    prompt_create_factory,
    subscription_create_factory,
    user_create_factory,
)

from user_service import repository, services
from user_service.enums import GenerationTaskStatus
from user_service.models import Base, Subscription


@dataclass
class DummyBananaClient:
    metadata: Dict[str, Any] | None = None
    last_payload: Dict[str, Any] | None = None

    def generate(self, payload: Dict[str, Any]) -> GeminiResult:
        self.last_payload = payload
        image = Image.new("RGB", (512, 512), color="blue")
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")
        self.metadata = {
            "model": "gemini-nano",
            "parameters": payload.get("parameters", {}),
        }
        return GeminiResult(image_bytes=buffer.getvalue(), metadata=self.metadata or {})

    def close(self) -> None:  # pragma: no cover - interface parity
        return None


class DummyNotifier:
    def __init__(self) -> None:
        self.status_events: List[Dict[str, Any]] = []
        self.dead_letters: List[Dict[str, Any]] = []
        self._locks: set[int] = set()

    async def connect(self) -> None:  # pragma: no cover - included for interface parity
        return None

    async def close(self) -> None:  # pragma: no cover - included for interface parity
        return None

    async def acquire_task(self, task_id: int) -> bool:
        if task_id in self._locks:
            return False
        self._locks.add(task_id)
        return True

    async def release_task(self, task_id: int) -> None:
        self._locks.discard(task_id)

    async def publish_status(self, status: str, payload: Dict[str, Any]) -> None:
        self.status_events.append({"status": status, **payload})

    async def publish_dead_letter(self, payload: Dict[str, Any]) -> None:
        self.dead_letters.append(payload)


@pytest.mark.asyncio
async def test_generation_task_pipeline_success(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'worker.db'}"
    settings = WorkerSettings(
        celery_broker_url="memory://",
        celery_result_backend="cache+memory://",
        redis_pubsub_url="redis://localhost:6379/0",
        database_url=database_url,
        s3_bucket="artifacts",
        s3_endpoint="http://localhost:9000",
        banana_model_key="model",
        banana_api_key="banana",
    )

    engine: AsyncEngine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    storage = InMemoryStorage()
    notifier = DummyNotifier()
    banana = DummyBananaClient()

    overrides = RuntimeOverrides(
        settings=settings,
        session_factory=session_factory,
        storage=storage,
        notifier=notifier,
        banana_client=banana,
    )

    await bootstrap.initialise(overrides)

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

    task_id: int | None = None
    subscription_id: int | None = None

    try:
        async with session_factory() as session:
            user = await repository.create_user(session, user_create_factory())
            prompt = await repository.create_prompt(session, prompt_create_factory())
            subscription = await services.activate_subscription(
                session, subscription_create_factory(user.id)
            )
            subscription_id = subscription.id
            task_input_key = "inputs/task.json"
            input_asset_url = f"s3://{settings.s3_bucket}/{task_input_key}"
            task_data = generation_task_create_factory(user.id, prompt.id)
            task = await repository.create_generation_task(
                session,
                task_data.model_copy(update={"input_asset_url": input_asset_url}),
            )
            task_id = task.id
            storage._objects[f"{settings.s3_bucket}/{task_input_key}"] = (
                b'{"prompt": "hello"}'
            )
            await session.commit()

        assert task_id is not None
        assert subscription_id is not None

        result = process_generation_task.apply(args=(task_id,)).get()

        async with session_factory() as session:
            refreshed = await repository.get_generation_task_by_id(session, task_id)
            assert refreshed is not None
            assert refreshed.status == GenerationTaskStatus.SUCCEEDED
            assert refreshed.result_asset_url is not None
            assert refreshed.result_parameters["thumbnail_url"].startswith("s3://")
            updated_subscription = await repository.get_subscription_by_id(
                session, subscription_id
            )
            assert isinstance(updated_subscription, Subscription)
            assert updated_subscription.quota_used == 1

        assert result["status"] == "succeeded"
        assert "result_url" in result
        assert notifier.dead_letters == []
        assert any(event["status"] == "running" for event in notifier.status_events)
        assert banana.last_payload is not None
        encoded_input = banana.last_payload["input_base64"]
        assert base64.b64decode(encoded_input) == b'{"prompt": "hello"}'
    finally:
        await bootstrap.shutdown()
        await engine.dispose()


@pytest.mark.asyncio
async def test_generation_task_pipeline_failure_refunds_quota(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'worker_failure.db'}"
    settings = WorkerSettings(
        celery_broker_url="memory://",
        celery_result_backend="cache+memory://",
        redis_pubsub_url="redis://localhost:6379/0",
        database_url=database_url,
        s3_bucket="artifacts",
        s3_endpoint="http://localhost:9000",
        banana_model_key="model",
        banana_api_key="banana",
    )

    engine: AsyncEngine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    storage = InMemoryStorage()
    notifier = DummyNotifier()

    class FailingBanana:
        def generate(self, payload: Dict[str, Any]) -> GeminiResult:
            raise RuntimeError("gemini down")

        def close(self) -> None:  # pragma: no cover - interface parity
            return None

    overrides = RuntimeOverrides(
        settings=settings,
        session_factory=session_factory,
        storage=storage,
        notifier=notifier,
        banana_client=FailingBanana(),
    )

    await bootstrap.initialise(overrides)

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = False

    task_id: int | None = None
    subscription_id: int | None = None

    try:
        async with session_factory() as session:
            user = await repository.create_user(session, user_create_factory())
            prompt = await repository.create_prompt(session, prompt_create_factory())
            subscription = await services.activate_subscription(
                session, subscription_create_factory(user.id)
            )
            subscription_id = subscription.id
            task_input_key = "inputs/failing.json"
            input_asset_url = f"s3://{settings.s3_bucket}/{task_input_key}"
            task_data = generation_task_create_factory(user.id, prompt.id)
            task = await repository.create_generation_task(
                session,
                task_data.model_copy(update={"input_asset_url": input_asset_url}),
            )
            task_id = task.id
            storage._objects[f"{settings.s3_bucket}/{task_input_key}"] = b"{}"
            await session.commit()

        assert task_id is not None
        assert subscription_id is not None

        result = process_generation_task.apply(args=(task_id,)).get()

        async with session_factory() as session:
            refreshed = await repository.get_generation_task_by_id(session, task_id)
            assert refreshed is not None
            assert refreshed.status == GenerationTaskStatus.FAILED
            updated_subscription = await repository.get_subscription_by_id(
                session, subscription_id
            )
            assert isinstance(updated_subscription, Subscription)
            assert updated_subscription.quota_used == 0

        assert result["status"] == "failed"
        assert result["error"] == "unexpected-error"
        assert notifier.dead_letters, "expected dead letter entry"
    finally:
        await bootstrap.shutdown()
        await engine.dispose()
