from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.modules.jobs.state import (
    InvalidJobTransition,
    JobStatus,
    transition_job,
    update_job_heartbeat,
)


def make_job(status):
    return SimpleNamespace(
        status=status,
        cancellation_requested=False,
        started_at=None,
        completed_at=None,
        heartbeat_at=None,
        error_code=None,
        error_message=None,
    )


def test_running_job_can_complete_after_cancellation_was_requested():
    job = make_job(JobStatus.RUNNING)
    transition_job(job, JobStatus.CANCEL_REQUESTED)
    transition_job(job, JobStatus.SUCCEEDED)

    assert job.status == "succeeded"
    assert job.completed_at is not None
    assert job.cancellation_requested is True


def test_failed_job_can_retry_without_erasing_attempt_history():
    job = make_job(JobStatus.FAILED)
    job.error_code = "provider_failed"
    job.error_message = "temporary"

    transition_job(job, JobStatus.QUEUED)

    assert job.status == "queued"
    assert job.error_code is None
    assert job.error_message is None


def test_terminal_job_cannot_be_restarted():
    with pytest.raises(InvalidJobTransition):
        transition_job(make_job(JobStatus.SUCCEEDED), JobStatus.QUEUED)


def test_heartbeat_updates_only_running_lifecycle_states():
    job = make_job(JobStatus.RUNNING)
    heartbeat_at = datetime(2026, 10, 9, tzinfo=UTC)

    update_job_heartbeat(job, heartbeat_at)

    assert job.heartbeat_at == heartbeat_at