from __future__ import annotations

import asyncio

from celery import Celery, signals

from .worker.bootstrap import initialise, shutdown
from .worker.config import WorkerSettings
from .worker.logging import configure_logging

_worker_settings = WorkerSettings()
configure_logging(_worker_settings.log_level)

celery_app = Celery(
    "generation_worker",
    broker=_worker_settings.celery_broker_url,
    backend=_worker_settings.celery_result_backend,
    include=["app.tasks"],
)

celery_app.conf.update(
    worker_send_task_events=True,
    task_send_sent_event=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_concurrency=4,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    task_default_queue="generation.tasks",
    task_default_delivery_mode="transient",
    worker_hijack_root_logger=False,
)

celery_app.conf.task_routes = {
    "app.tasks.process_generation_task": {"queue": "generation.tasks"},
}


@signals.worker_init.connect
def _on_worker_init(**_: object) -> None:
    asyncio.run(initialise())


@signals.worker_shutdown.connect
def _on_worker_shutdown(**_: object) -> None:
    asyncio.run(shutdown())
