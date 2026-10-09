# Backend Components

## 1. Suggested package layout

This is a proposed modular-monolith layout for the initial backend. Adapt it to the existing repository if one already exists; do not create a competing second structure without checking first.

```text
backend/
  app/
    main.py
    api/
      routes/
      schemas/
      dependencies.py
    core/
      config.py
      errors.py
      logging.py
      security.py
    db/
      session.py
      migrations/
      models/
      repositories/
    modules/
      workspaces/
      experiments/
      models/
      datasets/
      artifacts/
      jobs/
      compute/
      methods/
      environments/
      market_data/
      backtests/
      scale_intelligence/
      deployments/
      monitoring/
      audit/
    adapters/
      storage/
      queue/
      compute/
      environments/
    workers/
      runner.py
      handlers/
    tests/
  pyproject.toml
```

Keep the first implementation modular and testable. Separate deployable services only when scale, reliability, or team ownership justifies the operational complexity.

## 2. Module descriptions

### API and application layer
- FastAPI routes, Pydantic request/response schemas, authentication integration, authorization dependencies, error mapping, pagination, and versioning.
- Routes call application services; routes do not run training or provider API logic.

### Workspaces and authorization
- User identity integration, organizations/workspaces, membership, roles, ownership, and resource access checks.
- Every query and object operation must enforce workspace scope.

### Experiment core
- Experiment definitions, immutable run specifications, validation, run creation, lifecycle status, reproducibility references, and links to evaluations/backtests.
- An experiment is a record of work to investigate; a job is an asynchronous execution attempt. Do not conflate them.

### Model registry
- Model source and revision, model family/type, license/provenance metadata, artifact versions, evaluation summaries, and lifecycle state.
- Support externally hosted models without copying their weights automatically; cache/copy only when policy, licensing, and use case allow.

### Dataset registry
- Dataset source, version, schema, size, format, checksum, license/permission metadata, validation status, and artifact references.
- Preserve immutable dataset versions and record transformations as derived datasets with lineage.

### Artifact service and storage adapter
- Managed object storage integration, private-by-default objects, generated object keys, checksums, multipart upload where needed, temporary authorized URLs, artifact ownership, and retention.
- Define an interface so the provider can change without rewriting modules.

Suggested logical methods:
```python
class ObjectStorage:
    def create_upload_authorization(self, object_key: str, content_type: str, expires_in: int): ...
    def create_download_authorization(self, object_key: str, expires_in: int): ...
    def head_object(self, object_key: str): ...
    def delete_object(self, object_key: str): ...
```
This is illustrative, not a requirement to use these exact signatures.

### Job and queue system
- Job records, attempts, progress, status, heartbeat, logs, cancellation request, retries, and result references.
- Use a queue technology suitable for durable long-running workloads. Select it explicitly after considering operational complexity. FastAPI `BackgroundTasks` alone is not the job system for GPU training.
- Suggested states: `queued`, `provisioning`, `running`, `cancel_requested`, `succeeded`, `failed`, `cancelled`, `timed_out`, `lost`.
- Validate state transitions; retries create/record attempts instead of erasing history.

### Compute router
- Common compute request and result contracts, capability requirements, provider selection policy, provider health, usage/cost metadata when available, and provider job identifiers.
- Provider adapters implement provision/submit, status, logs if available, cancellation if supported, and cleanup.
- A provider's unsupported capability must be visible in the result; never promise uniform features that all providers do not support.

### Method engine
- Pluggable handlers for training, fine-tuning, evaluation, data preparation, and other supported work.
- Each method declares input schema, required compute capabilities, output artifacts, metrics, cancellation behavior, and reproducibility needs.
- Begin with a narrow vertical slice; do not implement every method family as empty placeholders.

### Environment manager and adapters
- Registry of environments, capabilities, schemas, data limits, and availability.
- Internal interface for symbol/instrument metadata, historical bars/ticks, live data stream when verified, and data quality.
- Dukascopy is the initial adapter. Isolate provider libraries and response shapes inside that adapter.
- Track terms/licensing, rate limits, data granularity, and live-data limitations as configuration/documentation, not assumptions.

### Market-data pipeline
- Ingest, normalize, validate, version, and store historical market data.
- Store metadata and data lineage in PostgreSQL; store large files/partitions in object storage or a suitable time-series store if justified.
- Detect gaps, duplicates, timestamp/time-zone issues, malformed rows, and symbol/metadata mismatches.
- Do not claim tick-level accuracy if only bars are available.

### Backtest and replay engine
- Deterministic simulation against versioned historical input.
- Define spread, slippage, fees, latency, order-fill assumptions, instrument metadata, and time boundaries explicitly.
- Track trades, equity curve, drawdown, returns, win/loss metrics, and data-quality warnings as appropriate.
- Separate simulation from live execution and keep assumptions visible in results.

### Scale intelligence
- Store scaling observations and predictions, fit/compare supported models, represent uncertainty, recommend next experiments, and track prediction-versus-actual calibration.
- Start with transparent baselines and tested regression/surrogate methods before advanced optimization.
- Do not claim reliable extrapolation without sufficient comparable observations.

### Deployment, serving and monitoring
- Deployment metadata, immutable artifact references, environment/runtime config, rollout state, health checks, prediction logs, outcome metrics, and model/version lineage.
- Keep generic model serving separate from any broker/execution integration.
- For Forex, signals, paper simulation, and live broker execution should be distinct modes with explicit capability and permission checks.

### Audit and observability
- Structured logs, request/job correlation IDs, metrics, trace hooks where useful, audit events, worker heartbeats, and actionable errors.
- Never log secrets or unrestricted signed URLs.

## 3. Storage contract

- PostgreSQL is the system of record for metadata and relationships.
- Managed object storage is the durable store for large files.
- Workers use short-lived authorized downloads/uploads; never assume a shared disk across compute providers.
- Registered datasets and final model artifacts are retained by default.
- Intermediate checkpoints, temporary data, and verbose logs follow configurable retention policies.
- Retention deletion must not remove a file still referenced by a protected artifact/version or active job.
- Use checksums and immutable versioned keys where feasible.
- Build orphan detection/cleanup for uploaded objects that never become registered artifacts.

## 4. Security and reliability requirements

- Validate MIME type, size, archive extraction paths, and supported file formats; defend against path traversal and decompression bombs.
- Do not accept arbitrary shell commands from untrusted users as the default execution model.
- Isolate user workloads and restrict network/file permissions.
- Use secrets manager/environment configuration for credentials.
- Apply timeouts, quotas, rate limits, and resource limits.
- Use database migrations; do not auto-create production schema as the only migration strategy.
- Use retries only for operations with defined idempotency semantics.
- Write unit tests for interfaces and state machines, integration tests for DB/storage/queue adapters, and end-to-end tests for a complete job lifecycle.
