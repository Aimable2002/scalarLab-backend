# Backend Implementation Roadmap

Build a vertical slice first. Keep each phase testable before expanding scope.

## Phase 0 — Repository and contract discovery

- Inspect the existing repository, frontend routes, TypeScript types, mock services, auth assumptions, and current backend code if any.
- Identify actual API expectations and distinguish implemented UI from mock-only functionality.
- Confirm Python version, dependency manager, deployment target, authentication approach, database, queue, and managed object storage provider.
- Document unresolved choices; do not silently guess.
- Produce a repository-specific implementation plan before large code changes.

**Acceptance:** architecture and API mapping reflect the actual repository; no parallel app is created accidentally.

## Phase 1 — Backend foundation

- FastAPI app/configuration, health/readiness endpoints, structured logging and request IDs.
- PostgreSQL connection, migrations, repository/service conventions.
- Workspace/resource authorization boundary.
- Error schema, settings validation, test setup, local development instructions.
- Queue and storage interfaces with configuration-driven adapters.

**Acceptance:** service starts reliably, migrations run, tests run, secrets are not committed, and health/readiness accurately reflect required dependencies.

## Phase 2 — Artifact and registry foundation

- Managed object storage adapter.
- Authorized temporary upload/download, upload finalization, checksums and artifact metadata.
- Dataset/model registries with immutable versions.
- Workspace access checks and retention metadata.
- Tests for unauthorized access, invalid uploads, missing objects, and incomplete uploads.

**Acceptance:** a user can register a dataset and model version, upload a file, verify it, and retrieve it only with authorized access.

## Phase 3 — Asynchronous job lifecycle

- Queue adapter and worker process.
- Job and attempt state machines.
- Progress updates, heartbeat, log capture/reference, cancellation, safe retry rules.
- Provider-neutral compute request/result contract and at least one concrete provider adapter only after selecting and verifying the provider.
- Worker scratch-space cleanup and artifact upload.

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
- Store raw/normalized files durably with version/lineage metadata.
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
