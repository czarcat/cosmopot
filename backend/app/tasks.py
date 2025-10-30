from __future__ import annotations

import random
import time

from .celery_app import celery_app


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
