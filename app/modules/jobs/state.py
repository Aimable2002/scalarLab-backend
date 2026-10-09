from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol


class JobStatus(StrEnum):
    QUEUED = "queued"
    PROVISIONING = "provisioning"
    RUNNING = "running"
    CANCEL_REQUESTED = "cancel_requested"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    LOST = "lost"


TERMINAL_STATUSES = {
    JobStatus.SUCCEEDED,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
    JobStatus.TIMED_OUT,
    JobStatus.LOST,
}

ALLOWED_TRANSITIONS = {
    JobStatus.QUEUED: {JobStatus.PROVISIONING, JobStatus.CANCELLED},
    JobStatus.PROVISIONING: {
        JobStatus.RUNNING,
        JobStatus.CANCEL_REQUESTED,
        JobStatus.FAILED,
    },
    JobStatus.RUNNING: {
        JobStatus.CANCEL_REQUESTED,
        JobStatus.SUCCEEDED,
        JobStatus.FAILED,
        JobStatus.TIMED_OUT,
        JobStatus.LOST,
    },
    JobStatus.CANCEL_REQUESTED: {
        JobStatus.CANCELLED,
        JobStatus.SUCCEEDED,
        JobStatus.FAILED,
    },
    JobStatus.FAILED: {JobStatus.QUEUED},
    JobStatus.LOST: {JobStatus.QUEUED},
    JobStatus.SUCCEEDED: set(),
    JobStatus.CANCELLED: set(),
    JobStatus.TIMED_OUT: set(),
}


class MutableJob(Protocol):
    status: str
    cancellation_requested: bool
    started_at: datetime | None
    completed_at: datetime | None
    heartbeat_at: datetime | None
    error_code: str | None
    error_message: str | None


class InvalidJobTransition(ValueError):
    pass


def transition_job(
    job: MutableJob,
    target: JobStatus,
    *,
    error_code: str | None = None,
    error_message: str | None = None,
    now: datetime | None = None,
) -> None:
    current = JobStatus(job.status)
    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidJobTransition(f"Cannot transition job from {current} to {target}")

    timestamp = now or datetime.now(UTC)
    job.status = target.value
    if target == JobStatus.CANCEL_REQUESTED:
        job.cancellation_requested = True
    if target == JobStatus.RUNNING and job.started_at is None:
        job.started_at = timestamp
    if target in TERMINAL_STATUSES:
        job.completed_at = timestamp
    if target == JobStatus.QUEUED:
        job.cancellation_requested = False
        job.error_code = None
        job.error_message = None
        job.completed_at = None
    else:
        job.error_code = error_code
        job.error_message = error_message


def update_job_heartbeat(job: MutableJob, now: datetime | None = None) -> None:
    if JobStatus(job.status) not in {JobStatus.PROVISIONING, JobStatus.RUNNING}:
        raise InvalidJobTransition("Only provisioning or running jobs can report a heartbeat")
    job.heartbeat_at = now or datetime.now(UTC)