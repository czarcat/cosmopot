from __future__ import annotations

import random
import time
from typing import Any

from celery import states

from .celery_app import celery_app
from .worker import bootstrap
from .worker.logging import get_logger
from .worker.processor import GenerationTaskProcessor

logger = get_logger(__name__)


@celery_app.task(name="app.tasks.ping")
def ping(message: str = "pong") -> dict[str, str]:
    return {"message": message}


@celery_app.task(name="app.tasks.compute_sum")
def compute_sum(a: int, b: int) -> int:
    time.sleep(1)
    return a + b


@celery_app.task(name="app.tasks.unreliable")
def unreliable_task() -> str:
    time.sleep(1)
    if random.random() < 0.5:
        raise RuntimeError("Unlucky run, try again")
    return "Completed"


@celery_app.task(name="app.tasks.process_generation_task", bind=True)
def process_generation_task(self, task_id: int) -> dict[str, Any]:
    runtime = bootstrap.get_runtime()
    processor = GenerationTaskProcessor(task_id, runtime)
    outcome = processor.run()
    result: dict[str, Any] = dict(outcome.details)
    result["status"] = outcome.status
    if outcome.status == "failed":
        logger.warning("generation-task-failed", task_id=task_id, details=result)
        self.update_state(state=states.FAILURE, meta=result)
    else:
        logger.info("generation-task-completed", task_id=task_id, details=result)
    return result
