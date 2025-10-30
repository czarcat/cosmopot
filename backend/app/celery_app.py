from __future__ import annotations

from celery import Celery

from .config import settings

celery_app = Celery(
    "devstack",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
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
)
