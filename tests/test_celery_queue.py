from uuid import uuid4

import pytest

from app.adapters.queue.celery import CANCEL_TASK_NAME, TASK_NAME, CeleryJobQueue
from app.core.config import Settings


class FakeCeleryApp:
    def __init__(self):
        self.calls = []

    def send_task(self, name, **kwargs):
        self.calls.append((name, kwargs))
        return type("Result", (), {"id": kwargs["task_id"]})()


def test_celery_queue_uses_job_id_as_task_id():
    application = FakeCeleryApp()
    queue = CeleryJobQueue(application)
    job_id = uuid4()

    dispatched_id = queue.enqueue_job(job_id)

    assert dispatched_id == str(job_id)
    assert application.calls == [
        (
            TASK_NAME,
            {"kwargs": {"job_id": str(job_id)}, "task_id": str(job_id)},
        )
    ]


def test_celery_queue_enqueues_provider_cancellation():
    application = FakeCeleryApp()
    queue = CeleryJobQueue(application)
    job_id = uuid4()

    dispatched_id = queue.enqueue_cancel(job_id)

    assert dispatched_id == f"cancel-{job_id}"
    assert application.calls == [
        (
            CANCEL_TASK_NAME,
            {"kwargs": {"job_id": str(job_id)}, "task_id": f"cancel-{job_id}"},
        )
    ]


def test_celery_queue_requires_explicit_redis_url():
    with pytest.raises(ValueError, match="REDIS_URL is required"):
        CeleryJobQueue.from_settings(Settings(_env_file=None))