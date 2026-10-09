# Backend Implementation Roadmap

Build a vertical slice first. Keep each phase testable before expanding scope.

## Phase 0 — Repository and contract discovery

- Inspect the existing repository, frontend routes, TypeScript types, mock services, auth assumptions, and current backend code if any.
- Identify actual API expectations and distinguish implemented UI from mock-only functionality.
- Confirm Python version, dependency manager, deployment target, and Modal account/function capabilities. V1 selects Supabase Auth and Database, Celery with Redis, S3-compatible object storage, and Modal as its first GPU provider.
- Document unresolved choices; do not silently guess.
- Produce a repository-specific implementation plan before large code changes.

**Acceptance:** architecture and API mapping reflect the actual repository; no parallel app is created accidentally.

## Phase 1 — Backend foundation

- FastAPI app/configuration, health/readiness endpoints, structured logging and request IDs.
- Supabase Database connection, migrations, repository/service conventions. The Supabase database is PostgreSQL-compatible; use its project connection string and keep credentials server-side.
- Supabase Auth token verification for API identity.
- Workspace/resource authorization boundary.
- Error schema, settings validation, test setup, local development instructions.
- Celery/Redis queue and S3-compatible storage interfaces with configuration-driven adapters.

**Acceptance:** service starts reliably, migrations run, tests run, secrets are not committed, and health/readiness accurately reflect required dependencies.

## Phase 2 — Artifact and registry foundation

- S3-compatible managed object storage adapter.
- Authorized temporary upload/download for final model weights and other platform-generated artifacts, upload finalization, checksums and artifact metadata.
- Dataset/model registries with immutable versions; V1 dataset versions are external provider references and metadata, not uploaded dataset files.
- Workspace access checks and retention metadata.
- Tests for unauthorized dataset references/artifact access, provider-reference validation, invalid model artifact uploads, missing objects, and incomplete uploads.

**Acceptance:** a user can register an externally hosted dataset version without uploading its bytes to platform storage, register a model, and upload/verify a trained model artifact that is retrievable only with authorized access.

## Phase 3 — Asynchronous job lifecycle

- Celery/Redis queue adapter and worker process.
- Job and attempt state machines.
- Progress updates, heartbeat, log capture/reference, cancellation, safe retry rules.
- Provider-neutral compute request/result contract and the selected Modal provider adapter; verify deployed function capabilities before enabling job submission.
- Download external datasets into temporary GPU-worker storage; clean scratch data on success, failure, and cancellation. Upload and verify required final model artifacts before GPU release.

V1 implementation supports the pinned Hugging Face dataset path. Kaggle remains registrable metadata only until its immutable revision-download capability is verified.

**Acceptance:** an integration test submits a job, observes status/progress/logs, cancels a supported running job, and retrieves the resulting artifacts. Failure/retry behavior is tested.

## Phase 4 — Experiment vertical slice

- Experiment and run records with immutable configuration snapshot.
- Link exact model/dataset versions.
- Submit evaluation or simple supported method as a background job.
- Persist metrics, artifacts, and execution metadata.
- Frontend-compatible endpoints based on actual frontend inspection.

**Acceptance:** user can create experiment → run job → inspect results → reproduce configuration.

## Phase 5 — Dukascopy market-data environment

- Verify applicable Dukascopy API/library, licensing, usage terms, data granularity, historical limits, and any live-data capability required.
- Implement environment registry and adapter.
- Normalize instrument metadata, timestamps, bars/ticks, and quality checks.
- For job-bound V1 datasets, retain provider references and version/lineage metadata; download to temporary GPU-worker storage and do not persist dataset copies in platform object storage. Persist platform-generated outputs only when required and permitted.
- Do not add broker execution unless separately verified and explicitly scoped.

**Acceptance:** an integration test ingests a bounded historical dataset, reports data quality, and reproduces the same normalized output from the same source/version/configuration.

## Phase 6 — Backtesting and evaluation

- Define backtest inputs, assumptions, and deterministic execution semantics.
- Implement a minimal supported strategy/model evaluation path.
- Persist summary metrics and store large outputs as artifacts.
- Add tests for time boundaries, missing data, fees/spread assumptions, reproducibility, and metric calculations.

**Acceptance:** same inputs and configuration produce repeatable results; reports clearly expose assumptions and data limitations.

## Phase 7 — Scale intelligence

- Build comparable experiment observations and metric definitions.
- Implement transparent baseline estimators and uncertainty handling.
- Store predictions, evidence runs, assumptions, and actual outcomes.
- Add calibration and prediction-versus-actual reports.
- Add active-learning/Bayesian optimization only after baseline data quality is demonstrated.

**Acceptance:** system can explain the evidence behind an estimate and reports insufficient evidence when appropriate.

## Phase 8 — Deployment and monitoring

- Model/runtime deployment records and artifact pinning.
- Health checks, operational metrics, domain metrics, prediction/outcome linkage.
- Paper/simulation deployment mode before any real-money execution integration.
- Explicit permission, safety, and provider-capability gates for live execution if ever added.

**Acceptance:** deployed version is traceable to a model artifact and monitoring data can be associated with its predictions/version.

## Phase 9 — Production hardening

- Tenant-isolation tests, quotas, secrets handling, rate limiting, backup/restore drills.
- Orphan artifact cleanup and retention scheduler.
- Observability, alerting, migrations/rollback, disaster recovery and provider failure testing.
- Load tests for API, queue, workers, and object storage patterns.
- Operational runbooks.

## Delivery rule

Do not mark a phase complete because files or endpoints exist. It is complete only when its acceptance criteria and automated tests pass. Prefer a narrow, end-to-end working path over broad empty scaffolding.
