# AI Experimentation Platform — Project Brief

## 1. Purpose

Build a platform that helps users move AI ideas through a measurable lifecycle:

**Idea → Plan → Experiment → Evaluate → Predict at scale → Validate/backtest → Deploy → Monitor → Learn**

The platform should help answer: *What can I learn about this AI idea cheaply before spending significantly more time and compute, and how reliable is that evidence when the system is scaled or deployed?*

The platform is not just a GPU rental interface, model registry, or training wrapper. Its value is the integrated workflow for planning experiments, running them on replaceable compute providers, preserving results, evaluating quality, estimating scale outcomes, validating in a real or simulated environment, and monitoring deployed systems.

## 2. Initial domain and future scope

### V1 domain: Forex research and validation

Dukascopy is the first market-data environment. V1 should make it possible to register/import data, build experiments, run jobs, manage model and dataset artifacts, and evaluate trading-oriented models using historical market data and backtesting where the required data and engine capabilities are verified.

Do not claim that access to market data automatically provides broker execution. **Market data and trade execution are separate interfaces and capabilities.** Do not implement live order placement against Dukascopy unless the relevant execution product/API and permissions have been explicitly verified.

### Future domains

The core should remain reusable for other environments such as crypto, equities, fraud detection, customer support, recommendations, vision, audio, and robotics. These are future extensibility targets, not promises that V1 already supports them.

## 3. Core capabilities

1. **Workspaces and access control** — users, organizations, roles, and ownership boundaries.
2. **Experiment management** — create experiment specifications, track status, versions, runs, parameters, and results.
3. **Model registry** — record model identity, source, revision, license metadata, artifact versions, and evaluation status.
4. **Dataset registry** — record source, version, schema, licensing/permissions, checksums, and stored artifacts.
5. **Method execution** — define pluggable methods such as fine-tuning, LoRA/QLoRA, RAG, distillation, evaluation, and domain-specific workflows. Only implement methods that have explicit contracts and tests.
6. **Compute routing** — submit asynchronous jobs to multiple GPU providers through one internal interface.
7. **Artifact storage** — managed cloud object storage for durable datasets, model weights, checkpoints, logs, and outputs.
8. **Scale intelligence** — estimate performance/cost/compute behavior from observed experiments, express uncertainty, suggest next experiments, and compare predictions with later results. Do not fabricate predictions when evidence is insufficient.
9. **Forex environment** — market-data adapter, data-quality checks, normalized historical data, and live-data capability only after verification.
10. **Backtesting and validation** — evaluate a strategy/model against historical data with reproducible configuration, assumptions, and metrics.
11. **Deployment and monitoring** — deployment records, model/service health, domain metrics, and prediction-versus-actual tracking. Real serving and live trading are distinct deployment modes.
12. **Auditability** — track important user actions, job transitions, artifact changes, and provider operations.

## 4. Fixed architecture decisions

- **Backend:** Python + FastAPI.
- **Execution:** asynchronous background jobs, not long-running work inside API request handlers.
- **Queues:** queue-backed dispatch, status updates, logs, retries where safe, and cancellation requests.
- **Compute:** multiple GPU providers behind one provider-neutral compute router.
- **Durable file storage:** managed cloud object storage, accessed through a provider-neutral storage interface.
- **GPU file access:** authorized, temporary downloads/uploads; workers must not depend on a shared filesystem across providers.
- **Database:** PostgreSQL for application records, metadata, state, relationships, and queryable metrics.
- **Retention:** retain registered datasets and final model artifacts. Intermediate checkpoints and temporary artifacts have configurable retention policies.
- **Storage security:** private objects by default; short-lived authorized access for workers; tenant/owner authorization enforced by the backend.
- **Environment abstraction:** Dukascopy is the first adapter, not a dependency spread throughout core business logic.
- **Separate interfaces:** environment/market-data access must not be conflated with execution/broker APIs.

## 5. Storage boundaries

| Data | System of record |
|---|---|
| Users, organizations, permissions, experiment/job records | PostgreSQL |
| Dataset/model metadata and versions | PostgreSQL |
| Large dataset files, model weights, checkpoints, reports, logs | Managed object storage |
| Job queue and transient coordination | Queue service; Redis may be used if selected |
| Worker scratch data | Temporary worker-local or attached scratch disk |
| Secrets and provider credentials | Environment/secret manager; never plain-text in source control |
| Large time-series outputs or exported reports | Object storage, with searchable summaries/metadata in PostgreSQL |

Never store large binary weights or full datasets directly in ordinary PostgreSQL rows. Store object keys and metadata in the database.

## 6. Non-goals for initial implementation

- Do not implement every model-training method at once.
- Do not invent undocumented provider APIs or claim a provider supports a capability before verification.
- Do not implement a trading broker or live order execution just because historical/live market data is available.
- Do not build a billing system before the core job, artifact, and ownership model works.
- Do not add a second persistent “goal” concept separate from the experiment/job model without a demonstrated requirement.
- Do not make the core depend directly on one GPU or storage vendor.
- Do not treat mock frontend data as proof of a backend contract; verify actual frontend pages/types before integration.

## 7. Definition of a useful first release

A user can create a workspace, register a dataset and model, create an experiment, submit a background job, see job status/logs, cancel a running job where supported, retrieve results and artifacts, and reproduce the experiment configuration. The first environment can ingest and validate the agreed Dukascopy data path. A backtest is reproducible from a defined data version and configuration. Access is isolated by workspace, and important state transitions are tested.

The first release should be end-to-end and testable, rather than a large set of disconnected placeholder modules.
