from uuid import UUID, uuid4
import re

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.adapters.compute.modal import ComputeProviderUnavailable, ModalComputeAdapter
from app.adapters.queue.celery import CeleryJobQueue
from app.adapters.storage.s3 import ObjectStorage
from app.core.config import Settings
from app.core.errors import ApiError
from app.core.security import Principal, get_current_principal
from app.modules.jobs.state import JobStatus, transition_job
from app.db.models import (
    Artifact,
    Dataset,
    DatasetVersion,
    Experiment,
    ExperimentRun,
    Job,
    JobAttempt,
    Membership,
    Model,
    ModelVersion,
    Workspace,
)
from app.db.session import get_session
from app.schemas import (
    DatasetCreate,
    DatasetOut,
    DatasetVersionCreate,
    ArtifactFinalize,
    ArtifactOut,
    ArtifactUploadAuthorizationCreate,
    ArtifactUploadAuthorizationOut,
    ModelCreate,
    ModelOut,
    ModelVersionCreate,
    ExperimentCreate,
    ExperimentOut,
    ExperimentRunCreate,
    ExperimentRunOut,
    JobLogsOut,
    JobOut,
    JobSubmissionOut,
    WorkspaceCreate,
    WorkspaceOut,
)

router = APIRouter(prefix="/api/v1")


def get_object_storage(request: Request) -> ObjectStorage:
    storage = request.app.state.object_storage
    if storage is None:
        raise ApiError(503, "object_storage_not_configured", "Object storage is not configured")
    return storage


def get_job_queue(request: Request) -> CeleryJobQueue:
    queue = request.app.state.job_queue
    if queue is None:
        raise ApiError(503, "job_queue_not_configured", "Redis job queue is not configured")
    return queue


def get_compute_provider(request: Request) -> ModalComputeAdapter:
    provider = request.app.state.compute_provider
    if provider is None:
        raise ApiError(503, "compute_provider_not_configured", "Modal compute is not configured")
    return provider


def require_workspace_member(
    session: Session,
    workspace_id: UUID,
    principal: Principal,
) -> Workspace:
    workspace = session.get(Workspace, workspace_id)
    is_member = session.scalar(
        select(Membership.id).where(
            Membership.workspace_id == workspace_id,
            Membership.user_id == principal.user_id,
        )
    )
    if workspace is None or is_member is None:
        raise ApiError(404, "workspace_not_found", "Workspace not found")
    return workspace


def require_final_model_artifact(
    session: Session,
    workspace_id: UUID,
    artifact_id: UUID | None,
) -> Artifact | None:
    if artifact_id is None:
        return None
    artifact = session.scalar(
        select(Artifact).where(
            Artifact.id == artifact_id,
            Artifact.workspace_id == workspace_id,
        )
    )
    if artifact is None:
        raise ApiError(404, "artifact_not_found", "Artifact not found")
    if artifact.status != "ready" or artifact.artifact_type != "final_model":
        raise ApiError(422, "model_artifact_not_ready", "Model versions require a ready final-model artifact")
    return artifact


def _commit_or_conflict(session: Session, code: str, message: str) -> None:
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ApiError(409, code, message) from None


def _validate_dataset_revision(provider: str, revision: str) -> None:
    if provider == "huggingface" and re.fullmatch(r"[0-9a-fA-F]{40}", revision) is None:
        raise ApiError(
            422,
            "immutable_revision_required",
            "Hugging Face dataset revisions must be immutable 40-character commit SHAs",
        )


@router.post(
    "/workspaces/{workspace_id}/artifacts/upload-authorizations",
    response_model=ArtifactUploadAuthorizationOut,
    status_code=status.HTTP_201_CREATED,
)
def create_artifact_upload_authorization(
    workspace_id: UUID,
    payload: ArtifactUploadAuthorizationCreate,
    request: Request,
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
    storage: ObjectStorage = Depends(get_object_storage),
) -> ArtifactUploadAuthorizationOut:
    require_workspace_member(session, workspace_id, principal)
    artifact_id = uuid4()
    object_key = f"workspaces/{workspace_id}/artifacts/{artifact_id}/{uuid4().hex}"
    retention_class = (
        "final_model" if payload.artifact_type == "final_model" else payload.artifact_type
    )
    artifact = Artifact(
        id=artifact_id,
        workspace_id=workspace_id,
        owner_resource_type="workspace",
        owner_resource_id=workspace_id,
        object_key=object_key,
        artifact_type=payload.artifact_type,
        content_type=payload.content_type,
        retention_class=retention_class,
    )
    session.add(artifact)
    settings: Settings = request.app.state.settings
    try:
        upload_url = storage.create_upload_authorization(
            object_key,
            payload.content_type,
            settings.object_storage_upload_url_ttl_seconds,
        )
        session.commit()
    except (BotoCoreError, ClientError):
        session.rollback()
        raise ApiError(503, "object_storage_unavailable", "Object storage is unavailable") from None
    return ArtifactUploadAuthorizationOut(
        artifact_id=artifact_id,
        upload_url=upload_url,
        expires_in=settings.object_storage_upload_url_ttl_seconds,
        required_headers={"Content-Type": payload.content_type},
    )


@router.post(
    "/workspaces/{workspace_id}/artifacts/{artifact_id}/finalize",
    response_model=ArtifactOut,
)
def finalize_artifact_upload(
    workspace_id: UUID,
    artifact_id: UUID,
    payload: ArtifactFinalize,
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
    storage: ObjectStorage = Depends(get_object_storage),
) -> Artifact:
    require_workspace_member(session, workspace_id, principal)
    artifact = session.scalar(
        select(Artifact).where(
            Artifact.id == artifact_id,
            Artifact.workspace_id == workspace_id,
        )
    )
    if artifact is None:
        raise ApiError(404, "artifact_not_found", "Artifact not found")
    if artifact.status == "ready":
        if artifact.size_bytes != payload.size_bytes:
            raise ApiError(409, "artifact_already_finalized", "Artifact was finalized with a different size")
        return artifact
    try:
        info = storage.head_object(artifact.object_key)
    except ClientError as error:
        code = error.response.get("Error", {}).get("Code")
        if code in {"404", "NoSuchKey", "NotFound"}:
            raise ApiError(409, "artifact_not_uploaded", "Artifact object has not been uploaded") from None
        raise ApiError(503, "object_storage_unavailable", "Object storage is unavailable") from None
    except BotoCoreError:
        raise ApiError(503, "object_storage_unavailable", "Object storage is unavailable") from None
    if info.size_bytes != payload.size_bytes or info.content_type != artifact.content_type:
        raise ApiError(422, "artifact_metadata_mismatch", "Uploaded object does not match declared metadata")
    artifact.size_bytes = info.size_bytes
    artifact.checksum_sha256 = info.checksum_sha256
    artifact.status = "ready"
    session.commit()
    session.refresh(artifact)
    return artifact


@router.post(
    "/workspaces/{workspace_id}/artifacts/{artifact_id}/download-authorization",
)
def create_artifact_download_authorization(
    workspace_id: UUID,
    artifact_id: UUID,
    request: Request,
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
    storage: ObjectStorage = Depends(get_object_storage),
) -> dict[str, str | int]:
    require_workspace_member(session, workspace_id, principal)
    artifact = session.scalar(
        select(Artifact).where(
            Artifact.id == artifact_id,
            Artifact.workspace_id == workspace_id,
            Artifact.status == "ready",
        )
    )
    if artifact is None:
        raise ApiError(404, "artifact_not_found", "Artifact not found")
    settings: Settings = request.app.state.settings
    try:
        download_url = storage.create_download_authorization(
            artifact.object_key,
            settings.object_storage_url_ttl_seconds,
        )
    except (BotoCoreError, ClientError):
        raise ApiError(503, "object_storage_unavailable", "Object storage is unavailable") from None
    return {"download_url": download_url, "expires_in": settings.object_storage_url_ttl_seconds}


@router.post("/workspaces", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: WorkspaceCreate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> Workspace:
    workspace = Workspace(name=payload.name.strip(), owner_user_id=principal.user_id)
    session.add(workspace)
    session.flush()
    session.add(
        Membership(workspace_id=workspace.id, user_id=principal.user_id, role="owner")
    )
    _commit_or_conflict(session, "workspace_conflict", "Workspace could not be created")
    session.refresh(workspace)
    return workspace


@router.get("/workspaces", response_model=list[WorkspaceOut])
def list_workspaces(
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> list[Workspace]:
    return list(
        session.scalars(
            select(Workspace)
            .join(Membership)
            .where(Membership.user_id == principal.user_id)
            .order_by(Workspace.created_at)
        )
    )


@router.post(
    "/workspaces/{workspace_id}/datasets",
    response_model=DatasetOut,
    status_code=status.HTTP_201_CREATED,
)
def register_dataset(
    workspace_id: UUID,
    payload: DatasetCreate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> Dataset:
    require_workspace_member(session, workspace_id, principal)
    _validate_dataset_revision(payload.provider, payload.revision)
    dataset = Dataset(
        workspace_id=workspace_id,
        name=payload.name.strip(),
        provider=payload.provider,
        source_id=payload.source_id.strip(),
        license_name=payload.license_name,
        created_by=principal.user_id,
    )
    dataset.versions.append(
        DatasetVersion(
            revision=payload.revision,
            file_path=payload.file_path,
            schema_summary=payload.schema_summary,
            checksum=payload.checksum,
            size_bytes=payload.size_bytes,
        )
    )
    session.add(dataset)
    _commit_or_conflict(
        session,
        "dataset_reference_exists",
        "This dataset reference or revision is already registered",
    )
    return session.scalar(
        select(Dataset)
        .options(selectinload(Dataset.versions))
        .where(Dataset.id == dataset.id)
    )


@router.get("/workspaces/{workspace_id}/datasets", response_model=list[DatasetOut])
def list_datasets(
    workspace_id: UUID,
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> list[Dataset]:
    require_workspace_member(session, workspace_id, principal)
    return list(
        session.scalars(
            select(Dataset)
            .options(selectinload(Dataset.versions))
            .where(Dataset.workspace_id == workspace_id)
            .order_by(Dataset.created_at)
        )
    )


@router.post(
    "/workspaces/{workspace_id}/datasets/{dataset_id}/versions",
    response_model=DatasetOut,
    status_code=status.HTTP_201_CREATED,
)
def register_dataset_version(
    workspace_id: UUID,
    dataset_id: UUID,
    payload: DatasetVersionCreate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> Dataset:
    require_workspace_member(session, workspace_id, principal)
    dataset = session.scalar(
        select(Dataset)
        .options(selectinload(Dataset.versions))
        .where(Dataset.id == dataset_id, Dataset.workspace_id == workspace_id)
    )
    if dataset is None:
        raise ApiError(404, "dataset_not_found", "Dataset not found")
    _validate_dataset_revision(dataset.provider, payload.revision)
    dataset.versions.append(
        DatasetVersion(
            revision=payload.revision,
            file_path=payload.file_path,
            schema_summary=payload.schema_summary,
            checksum=payload.checksum,
            size_bytes=payload.size_bytes,
        )
    )
    _commit_or_conflict(
        session,
        "dataset_revision_exists",
        "This dataset revision is already registered",
    )
    return dataset


@router.post(
    "/workspaces/{workspace_id}/models",
    response_model=ModelOut,
    status_code=status.HTTP_201_CREATED,
)
def register_model(
    workspace_id: UUID,
    payload: ModelCreate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> Model:
    require_workspace_member(session, workspace_id, principal)
    require_final_model_artifact(session, workspace_id, payload.artifact_id)
    model = Model(
        workspace_id=workspace_id,
        name=payload.name.strip(),
        source_type=payload.source_type,
        source_id=payload.source_id.strip(),
        license_name=payload.license_name,
        created_by=principal.user_id,
    )
    model.versions.append(
        ModelVersion(
            revision=payload.revision,
            source_uri=payload.source_uri,
            checksum=payload.checksum,
            artifact_id=payload.artifact_id,
        )
    )
    session.add(model)
    _commit_or_conflict(session, "model_conflict", "Model could not be registered")
    return session.scalar(
        select(Model)
        .options(selectinload(Model.versions))
        .where(Model.id == model.id)
    )


@router.get("/workspaces/{workspace_id}/models", response_model=list[ModelOut])
def list_models(
    workspace_id: UUID,
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> list[Model]:
    require_workspace_member(session, workspace_id, principal)
    return list(
        session.scalars(
            select(Model)
            .options(selectinload(Model.versions))
            .where(Model.workspace_id == workspace_id)
            .order_by(Model.created_at)
        )
    )


@router.post(
    "/workspaces/{workspace_id}/models/{model_id}/versions",
    response_model=ModelOut,
    status_code=status.HTTP_201_CREATED,
)
def register_model_version(
    workspace_id: UUID,
    model_id: UUID,
    payload: ModelVersionCreate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> Model:
    require_workspace_member(session, workspace_id, principal)
    model = session.scalar(
        select(Model)
        .options(selectinload(Model.versions))
        .where(Model.id == model_id, Model.workspace_id == workspace_id)
    )
    if model is None:
        raise ApiError(404, "model_not_found", "Model not found")
    require_final_model_artifact(session, workspace_id, payload.artifact_id)
    model.versions.append(
        ModelVersion(
            revision=payload.revision,
            source_uri=payload.source_uri,
            checksum=payload.checksum,
            artifact_id=payload.artifact_id,
        )
    )
    _commit_or_conflict(session, "model_revision_exists", "Model revision already exists")
    return model


@router.post(
    "/workspaces/{workspace_id}/experiments",
    response_model=ExperimentOut,
    status_code=status.HTTP_201_CREATED,
)
def create_experiment(
    workspace_id: UUID,
    payload: ExperimentCreate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> Experiment:
    require_workspace_member(session, workspace_id, principal)
    experiment = Experiment(
        workspace_id=workspace_id,
        name=payload.name.strip(),
        description=payload.description,
        created_by=principal.user_id,
    )
    session.add(experiment)
    session.commit()
    session.refresh(experiment)
    return experiment


@router.get(
    "/workspaces/{workspace_id}/experiments",
    response_model=list[ExperimentOut],
)
def list_experiments(
    workspace_id: UUID,
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> list[Experiment]:
    require_workspace_member(session, workspace_id, principal)
    return list(
        session.scalars(
            select(Experiment)
            .where(Experiment.workspace_id == workspace_id)
            .order_by(Experiment.created_at)
        )
    )


@router.post(
    "/workspaces/{workspace_id}/experiments/{experiment_id}/runs",
    response_model=JobSubmissionOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def submit_experiment_run(
    workspace_id: UUID,
    experiment_id: UUID,
    payload: ExperimentRunCreate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
    queue: CeleryJobQueue = Depends(get_job_queue),
    storage: ObjectStorage = Depends(get_object_storage),
    compute: ModalComputeAdapter = Depends(get_compute_provider),
) -> JobSubmissionOut:
    require_workspace_member(session, workspace_id, principal)
    experiment = session.scalar(
        select(Experiment).where(
            Experiment.id == experiment_id,
            Experiment.workspace_id == workspace_id,
        )
    )
    if experiment is None:
        raise ApiError(404, "experiment_not_found", "Experiment not found")
    dataset_version = session.scalar(
        select(DatasetVersion)
        .join(Dataset, DatasetVersion.dataset_id == Dataset.id)
        .where(
            DatasetVersion.id == payload.dataset_version_id,
            Dataset.workspace_id == workspace_id,
        )
    )
    if dataset_version is None:
        raise ApiError(404, "dataset_version_not_found", "Dataset version not found")
    if dataset_version.dataset.provider != "huggingface":
        raise ApiError(
            422,
            "dataset_provider_revision_unsupported",
            "V1 jobs require a pinned Hugging Face dataset revision",
        )
    if not dataset_version.file_path:
        raise ApiError(422, "dataset_file_required", "Dataset version must identify a provider file")
    if not dataset_version.file_path.lower().endswith((".csv", ".parquet", ".pq")):
        raise ApiError(422, "unsupported_dataset_format", "Forex baseline supports CSV and Parquet")

    run_id = uuid4()
    job_id = uuid4()
    artifact_id = uuid4()
    object_key = f"workspaces/{workspace_id}/artifacts/{artifact_id}/{uuid4().hex}"
    configuration = {
        "method": payload.method,
        "dataset_version_id": str(dataset_version.id),
        "dataset_revision": dataset_version.revision,
        "dataset_file_path": dataset_version.file_path,
        "target": "next_bar_close_up",
        "train_fraction": 0.8,
    }
    run = ExperimentRun(
        id=run_id,
        experiment_id=experiment.id,
        dataset_version_id=dataset_version.id,
        method=payload.method,
        configuration_snapshot=configuration,
        status=JobStatus.QUEUED.value,
    )
    job = Job(
        id=job_id,
        workspace_id=workspace_id,
        run_id=run_id,
        artifact_id=artifact_id,
        job_type=payload.method,
        status=JobStatus.QUEUED.value,
    )
    artifact = Artifact(
        id=artifact_id,
        workspace_id=workspace_id,
        owner_resource_type="job",
        owner_resource_id=job_id,
        object_key=object_key,
        artifact_type="final_model",
        content_type="application/octet-stream",
        retention_class="final_model",
    )
    session.add_all([run, job, artifact])
    session.commit()
    try:
        queue.enqueue_job(job_id)
    except Exception:
        transition_job(
            job,
            JobStatus.FAILED,
            error_code="queue_dispatch_failed",
            error_message="Job could not be dispatched",
        )
        run.status = JobStatus.FAILED.value
        run.completed_at = job.completed_at
        session.commit()
        raise ApiError(503, "queue_unavailable", "Job queue is unavailable") from None
    session.refresh(run)
    session.refresh(job)
    return JobSubmissionOut(run=run, job=job)


@router.get(
    "/workspaces/{workspace_id}/jobs/{job_id}",
    response_model=JobOut,
)
def get_job(
    workspace_id: UUID,
    job_id: UUID,
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> Job:
    require_workspace_member(session, workspace_id, principal)
    job = session.scalar(
        select(Job).where(Job.id == job_id, Job.workspace_id == workspace_id)
    )
    if job is None:
        raise ApiError(404, "job_not_found", "Job not found")
    return job


@router.post(
    "/workspaces/{workspace_id}/jobs/{job_id}/cancel",
    response_model=JobOut,
)
def cancel_job(
    workspace_id: UUID,
    job_id: UUID,
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
    queue: CeleryJobQueue = Depends(get_job_queue),
) -> Job:
    require_workspace_member(session, workspace_id, principal)
    job = session.scalar(
        select(Job).where(Job.id == job_id, Job.workspace_id == workspace_id)
    )
    if job is None:
        raise ApiError(404, "job_not_found", "Job not found")
    if job.status == JobStatus.QUEUED.value:
        transition_job(job, JobStatus.CANCELLED)
        run = session.get(ExperimentRun, job.run_id)
        if run is not None:
            run.status = JobStatus.CANCELLED.value
            run.completed_at = job.completed_at
        session.commit()
        return job
    if job.status in {JobStatus.PROVISIONING.value, JobStatus.RUNNING.value}:
        transition_job(job, JobStatus.CANCEL_REQUESTED)
        session.commit()
        try:
            queue.enqueue_cancel(job.id)
        except Exception:
            pass
    return job


@router.get(
    "/workspaces/{workspace_id}/jobs/{job_id}/logs",
    response_model=JobLogsOut,
)
async def get_job_logs(
    workspace_id: UUID,
    job_id: UUID,
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
    compute: ModalComputeAdapter = Depends(get_compute_provider),
) -> JobLogsOut:
    require_workspace_member(session, workspace_id, principal)
    job = session.scalar(
        select(Job).where(Job.id == job_id, Job.workspace_id == workspace_id)
    )
    if job is None:
        raise ApiError(404, "job_not_found", "Job not found")
    attempt = session.scalar(
        select(JobAttempt)
        .where(JobAttempt.job_id == job_id)
        .order_by(JobAttempt.attempt_number.desc())
    )
    if attempt is None or attempt.provider_job_id is None:
        return JobLogsOut(logs=[])
    try:
        logs = await compute.tail_logs(attempt.provider_job_id)
    except ComputeProviderUnavailable:
        raise ApiError(503, "compute_provider_unavailable", "Modal is unavailable") from None
    return JobLogsOut(logs=logs)