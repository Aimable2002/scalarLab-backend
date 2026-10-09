from datetime import UTC, datetime
from functools import lru_cache
from uuid import UUID, uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.adapters.compute.modal import (
    ComputeProviderUnavailable,
    ModalCallState,
    ModalComputeAdapter,
)
from app.adapters.queue.celery import CANCEL_TASK_NAME, POLL_TASK_NAME, TASK_NAME
from app.adapters.storage.s3 import S3CompatibleStorage
from app.core.config import Settings, get_settings
from app.db.models import (
    Artifact,
    Dataset,
    DatasetVersion,
    Experiment,
    ExperimentRun,
    Job,
    JobAttempt,
    Model,
    ModelVersion,
)
from app.modules.jobs.state import (
    JobStatus,
    TERMINAL_STATUSES,
    transition_job,
    update_job_heartbeat,
)
from app.worker.celery_app import celery_app


@lru_cache(maxsize=1)
def _engine():
    settings = get_settings()
    if settings.database_url is None:
        raise RuntimeError("SUPABASE_DATABASE_URL is required in the Celery worker")
    return create_engine(settings.database_url, pool_pre_ping=True)


@lru_cache(maxsize=1)
def _storage() -> S3CompatibleStorage:
    return S3CompatibleStorage.from_settings(get_settings())


def _compute(settings: Settings) -> ModalComputeAdapter:
    return ModalComputeAdapter.from_settings(settings)


def _schedule_poll(job_id: UUID, delay_seconds: int = 10) -> None:
    poll_remote_job.apply_async(
        kwargs={"job_id": str(job_id)},
        countdown=delay_seconds,
        task_id=f"poll-{job_id}-{uuid4().hex}",
    )


def _finish_failed_job(
    session: Session,
    job: Job,
    run: ExperimentRun,
    attempt: JobAttempt,
    error_code: str,
    message: str,
    status: JobStatus = JobStatus.FAILED,
) -> None:
    transition_job(job, status, error_code=error_code, error_message=message)
    run.status = status.value
    run.completed_at = job.completed_at
    attempt.status = status.value
    attempt.failure_code = error_code
    attempt.ended_at = job.completed_at
    session.commit()


def _load_run_inputs(session: Session, job: Job):
    run = session.get(ExperimentRun, job.run_id)
    if run is None:
        raise ValueError("Job run does not exist")
    experiment = session.get(Experiment, run.experiment_id)
    dataset_version = session.get(DatasetVersion, run.dataset_version_id)
    if experiment is None or dataset_version is None:
        raise ValueError("Job inputs are no longer available")
    dataset = session.get(Dataset, dataset_version.dataset_id)
    artifact = session.get(Artifact, job.artifact_id)
    if dataset is None or artifact is None or dataset_version.file_path is None:
        raise ValueError("Job dataset or output artifact is incomplete")
    return run, experiment, dataset_version, dataset, artifact


@celery_app.task(name=TASK_NAME)
def execute_job(job_id: str) -> None:
    parsed_job_id = UUID(job_id)
    settings = get_settings()
    compute = _compute(settings)

    with Session(_engine()) as session:
        job = session.scalar(select(Job).where(Job.id == parsed_job_id).with_for_update())
        if job is None or job.status != JobStatus.QUEUED.value:
            return
        transition_job(job, JobStatus.PROVISIONING)
        job.current_attempt += 1
        attempt = JobAttempt(
            job_id=job.id,
            attempt_number=job.current_attempt,
            provider_id="modal",
            status=JobStatus.PROVISIONING.value,
        )
        session.add(attempt)
        session.commit()
        current_attempt_id = attempt.id
        try:
            run, experiment, dataset_version, dataset, artifact = _load_run_inputs(session, job)
        except ValueError:
            run = session.get(ExperimentRun, job.run_id)
            if run is not None:
                _finish_failed_job(
                    session,
                    job,
                    run,
                    attempt,
                    "job_inputs_unavailable",
                    "Job inputs are no longer available",
                )
            return
        if dataset.provider != "huggingface":
            _finish_failed_job(
                session,
                job,
                run,
                attempt,
                "unsupported_dataset_provider",
                "This job requires a pinned Hugging Face revision",
            )
            return
        try:
            upload_url = _storage().create_upload_authorization(
                artifact.object_key,
                artifact.content_type,
                settings.object_storage_upload_url_ttl_seconds,
            )
        except Exception:
            _finish_failed_job(
                session,
                job,
                run,
                attempt,
                "artifact_authorization_failed",
                "Object storage could not authorize the model upload",
            )
            return
        input_payload = {
            "dataset": {
                "provider": dataset.provider,
                "source_id": dataset.source_id,
                "revision": dataset_version.revision,
                "file_path": dataset_version.file_path,
            },
            "artifact_id": str(artifact.id),
            "artifact_upload_url": upload_url,
        }

    try:
        provider_job_id = compute.submit(input_payload)
    except Exception:
        with Session(_engine()) as session:
            job = session.get(Job, parsed_job_id)
            attempt = session.get(JobAttempt, current_attempt_id)
            run = session.get(ExperimentRun, job.run_id) if job else None
            if job is not None and attempt is not None and run is not None:
                _finish_failed_job(
                    session,
                    job,
                    run,
                    attempt,
                    "modal_submit_failed",
                    "Modal could not accept the job",
                )
        return

    with Session(_engine()) as session:
        job = session.get(Job, parsed_job_id)
        attempt = session.get(JobAttempt, current_attempt_id)
        run = session.get(ExperimentRun, job.run_id) if job else None
        if job is None or attempt is None or run is None:
            compute.cancel(provider_job_id)
            return
        attempt.provider_job_id = provider_job_id
        attempt.status = JobStatus.RUNNING.value
        if job.status == JobStatus.PROVISIONING.value:
            transition_job(job, JobStatus.RUNNING)
        run.status = job.status
        run.started_at = job.started_at
        session.commit()
        if job.cancellation_requested:
            try:
                compute.cancel(provider_job_id)
            except ComputeProviderUnavailable:
                pass

    _schedule_poll(parsed_job_id)


@celery_app.task(name=POLL_TASK_NAME)
def poll_remote_job(job_id: str) -> None:
    parsed_job_id = UUID(job_id)
    settings = get_settings()
    compute = _compute(settings)

    with Session(_engine()) as session:
        job = session.get(Job, parsed_job_id)
        if job is None or JobStatus(job.status) in TERMINAL_STATUSES:
            return
        attempt = session.scalar(
            select(JobAttempt)
            .where(JobAttempt.job_id == job.id)
            .order_by(JobAttempt.attempt_number.desc())
        )
        if attempt is None or attempt.provider_job_id is None:
            _schedule_poll(parsed_job_id, delay_seconds=30)
            return
        provider_job_id = attempt.provider_job_id
        cancellation_requested = job.cancellation_requested

    try:
        provider_result = compute.status(provider_job_id)
    except ComputeProviderUnavailable:
        _schedule_poll(parsed_job_id, delay_seconds=30)
        return

    if provider_result.state == ModalCallState.RUNNING:
        if cancellation_requested:
            try:
                compute.cancel(provider_job_id)
            except ComputeProviderUnavailable:
                pass
        with Session(_engine()) as session:
            job = session.get(Job, parsed_job_id)
            if job is not None and job.status in {
                JobStatus.PROVISIONING.value,
                JobStatus.RUNNING.value,
            }:
                if job.status == JobStatus.PROVISIONING.value:
                    transition_job(job, JobStatus.RUNNING)
                update_job_heartbeat(job)
                session.commit()
        _schedule_poll(parsed_job_id)
        return

    with Session(_engine()) as session:
        job = session.get(Job, parsed_job_id)
        if job is None or JobStatus(job.status) in TERMINAL_STATUSES:
            return
        run = session.get(ExperimentRun, job.run_id)
        attempt = session.scalar(
            select(JobAttempt)
            .where(JobAttempt.job_id == job.id)
            .order_by(JobAttempt.attempt_number.desc())
        )
        if run is None or attempt is None:
            return

        if provider_result.state == ModalCallState.SUCCEEDED:
            _complete_successful_job(session, job, run, attempt, provider_result.output)
            return

        if job.cancellation_requested:
            terminal_status = JobStatus.CANCELLED
            error_code = "job_cancelled"
            error_message = "Job was cancelled by request"
        elif provider_result.state == ModalCallState.TIMED_OUT:
            terminal_status = JobStatus.TIMED_OUT
            error_code = "modal_timeout"
            error_message = "Modal job timed out"
        elif provider_result.state == ModalCallState.LOST:
            terminal_status = JobStatus.LOST
            error_code = "modal_output_expired"
            error_message = "Modal job output is no longer available"
        else:
            terminal_status = JobStatus.FAILED
            error_code = "modal_execution_failed"
            error_message = "Modal job failed"
        _finish_failed_job(
            session,
            job,
            run,
            attempt,
            error_code,
            error_message,
            terminal_status,
        )


def _complete_successful_job(
    session: Session,
    job: Job,
    run: ExperimentRun,
    attempt: JobAttempt,
    output: object,
) -> None:
    if not isinstance(output, dict):
        _finish_failed_job(
            session,
            job,
            run,
            attempt,
            "invalid_provider_result",
            "Modal returned an invalid result",
        )
        return
    artifact = session.get(Artifact, job.artifact_id)
    if artifact is None or output.get("artifact_id") != str(job.artifact_id):
        _finish_failed_job(
            session,
            job,
            run,
            attempt,
            "artifact_reference_mismatch",
            "Modal result did not reference the expected model artifact",
        )
        return
    try:
        object_info = _storage().head_object(artifact.object_key)
    except Exception:
        _finish_failed_job(
            session,
            job,
            run,
            attempt,
            "artifact_verification_failed",
            "Uploaded model artifact could not be verified",
        )
        return
    if object_info.size_bytes != output.get("size_bytes"):
        _finish_failed_job(
            session,
            job,
            run,
            attempt,
            "artifact_size_mismatch",
            "Uploaded model artifact size did not match the Modal result",
        )
        return

    artifact.size_bytes = object_info.size_bytes
    artifact.checksum_sha256 = output.get("checksum_sha256")
    artifact.status = "ready"
    experiment = session.get(Experiment, run.experiment_id)
    if experiment is not None:
        model = Model(
            workspace_id=job.workspace_id,
            name=f"{experiment.name} baseline model",
            source_type="platform",
            source_id=f"scalar-lab/{run.id}",
            created_by=experiment.created_by,
        )
        session.add(model)
        session.flush()
        model_version = ModelVersion(
            id=uuid4(),
            model_id=model.id,
            revision=f"run-{run.id}",
            checksum=artifact.checksum_sha256,
            artifact_id=artifact.id,
            status="ready",
        )
        session.add(model_version)
        run.model_version_id = model_version.id
    transition_job(job, JobStatus.SUCCEEDED)
    job.progress = 100
    run.status = JobStatus.SUCCEEDED.value
    run.metrics_summary = output.get("metrics")
    run.completed_at = job.completed_at
    attempt.status = JobStatus.SUCCEEDED.value
    attempt.ended_at = job.completed_at
    session.commit()


@celery_app.task(name=CANCEL_TASK_NAME)
def cancel_job(job_id: str) -> None:
    parsed_job_id = UUID(job_id)
    with Session(_engine()) as session:
        job = session.get(Job, parsed_job_id)
        if job is None or job.status != JobStatus.CANCEL_REQUESTED.value:
            return
        attempt = session.scalar(
            select(JobAttempt)
            .where(JobAttempt.job_id == job.id)
            .order_by(JobAttempt.attempt_number.desc())
        )
        if attempt is None or attempt.provider_job_id is None:
            _schedule_poll(parsed_job_id)
            return
        provider_job_id = attempt.provider_job_id

    try:
        _compute(get_settings()).cancel(provider_job_id)
    except ComputeProviderUnavailable:
        pass
    _schedule_poll(parsed_job_id)