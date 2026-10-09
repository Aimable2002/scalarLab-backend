from datetime import datetime
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkspaceCreate(StrictSchema):
    name: str = Field(min_length=1, max_length=200)


class WorkspaceOut(BaseModel):
    id: UUID
    name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DatasetVersionCreate(StrictSchema):
    revision: str = Field(min_length=1, max_length=256)
    file_path: str | None = Field(default=None, min_length=1, max_length=1024)
    schema_summary: dict[str, JsonValue] | None = None
    checksum: str | None = Field(default=None, max_length=128)
    size_bytes: int | None = Field(default=None, ge=0)


class DatasetCreate(DatasetVersionCreate):
    name: str = Field(min_length=1, max_length=200)
    provider: Literal["kaggle", "huggingface"]
    source_id: str = Field(min_length=1, max_length=512)
    license_name: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def require_immutable_huggingface_revision(self):
        if self.provider == "huggingface" and re.fullmatch(r"[0-9a-fA-F]{40}", self.revision) is None:
            raise ValueError("Hugging Face dataset revisions must be immutable 40-character commit SHAs")
        return self


class DatasetVersionOut(BaseModel):
    id: UUID
    revision: str
    file_path: str | None
    schema_summary: dict[str, JsonValue] | None
    checksum: str | None
    size_bytes: int | None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DatasetOut(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    provider: str
    source_id: str
    license_name: str | None
    created_at: datetime
    versions: list[DatasetVersionOut]

    model_config = ConfigDict(from_attributes=True)


class ModelVersionCreate(StrictSchema):
    revision: str = Field(min_length=1, max_length=256)
    source_uri: str | None = Field(default=None, max_length=2048)
    checksum: str | None = Field(default=None, max_length=128)
    artifact_id: UUID | None = None


class ModelCreate(ModelVersionCreate):
    name: str = Field(min_length=1, max_length=200)
    source_type: Literal["huggingface", "external", "platform"]
    source_id: str = Field(min_length=1, max_length=512)
    license_name: str | None = Field(default=None, max_length=200)


class ModelVersionOut(BaseModel):
    id: UUID
    revision: str
    source_uri: str | None
    checksum: str | None
    artifact_id: UUID | None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ModelOut(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    source_type: str
    source_id: str
    license_name: str | None
    created_at: datetime
    versions: list[ModelVersionOut]

    model_config = ConfigDict(from_attributes=True)


class ArtifactUploadAuthorizationCreate(StrictSchema):
    artifact_type: Literal[
        "final_model", "intermediate_checkpoint", "temporary_job_output", "logs", "export"
    ]
    content_type: str = Field(min_length=1, max_length=255)


class ArtifactUploadAuthorizationOut(BaseModel):
    artifact_id: UUID
    upload_url: str
    expires_in: int
    required_headers: dict[str, str]


class ArtifactFinalize(StrictSchema):
    size_bytes: int = Field(gt=0)


class ArtifactOut(BaseModel):
    id: UUID
    workspace_id: UUID
    artifact_type: str
    content_type: str
    size_bytes: int | None
    checksum_sha256: str | None
    retention_class: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExperimentCreate(StrictSchema):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class ExperimentOut(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    description: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExperimentRunCreate(StrictSchema):
    dataset_version_id: UUID
    method: Literal["forex_baseline"]


class ExperimentRunOut(BaseModel):
    id: UUID
    experiment_id: UUID
    dataset_version_id: UUID
    model_version_id: UUID | None
    method: str
    status: str
    configuration_snapshot: dict[str, JsonValue]
    metrics_summary: dict[str, JsonValue] | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JobOut(BaseModel):
    id: UUID
    run_id: UUID
    artifact_id: UUID
    job_type: str
    status: str
    progress: int
    cancellation_requested: bool
    current_attempt: int
    error_code: str | None
    error_message: str | None
    queued_at: datetime
    started_at: datetime | None
    heartbeat_at: datetime | None
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class JobLogsOut(BaseModel):
    logs: list[dict[str, JsonValue]]


class JobSubmissionOut(BaseModel):
    run: ExperimentRunOut
    job: JobOut