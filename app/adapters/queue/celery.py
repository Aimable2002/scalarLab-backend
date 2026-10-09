from collections.abc import Callable
from functools import lru_cache
from uuid import UUID

from celery import Celery

from app.core.config import Settings

TASK_NAME = "scalar_lab.execute_job"
CANCEL_TASK_NAME = "scalar_lab.cancel_job"
POLL_TASK_NAME = "scalar_lab.poll_job"


@lru_cache(maxsize=4)
def create_celery_app(redis_url: str) -> Celery:
    application = Celery("scalar_lab", broker=redis_url, include=["app.worker.tasks"])
    application.conf.update(
        accept_content=["json"],
        task_serializer="json",
        result_serializer="json",
        task_ignore_result=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        broker_connection_retry_on_startup=True,
    )
    return application


class CeleryJobQueue:
    def __init__(self, application: Celery) -> None:
        self.application = application

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        app_factory: Callable[[str], Celery] = create_celery_app,
    ) -> "CeleryJobQueue":
        if settings.redis_url is None:
            raise ValueError("REDIS_URL is required to configure the job queue")
        return cls(app_factory(settings.redis_url.get_secret_value()))

    def enqueue_job(self, job_id: UUID) -> str:
        result = self.application.send_task(
            TASK_NAME,
            kwargs={"job_id": str(job_id)},
            task_id=str(job_id),
        )
        return result.id

    def enqueue_cancel(self, job_id: UUID) -> str:
        result = self.application.send_task(
            CANCEL_TASK_NAME,
            kwargs={"job_id": str(job_id)},
            task_id=f"cancel-{job_id}",
        )
        return result.id