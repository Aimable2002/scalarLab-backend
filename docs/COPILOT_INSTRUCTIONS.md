# Instructions for GitHub Copilot

Read `AGENTS.md` and all relevant files in `docs/` before implementing or changing backend architecture.

## Rules

1. Inspect the current repository before writing code. Preserve existing working conventions unless there is a documented reason to change them.
2. Do not create a second application, duplicate models, or parallel architecture without first identifying what already exists.
3. Treat `PROJECT_BRIEF.md`, `SYSTEM_ARCHITECTURE.md`, `COMPONENT_RELATIONSHIPS.md`, and `DATA_AND_API_CONTRACTS.md` as the source of architectural intent. If they conflict with the actual repository, report the conflict and propose a minimal resolution before making broad changes.
4. Implement incrementally according to `IMPLEMENTATION_ROADMAP.md`. Do not scaffold every module as an empty placeholder.
5. Use Python + FastAPI. Keep long-running training, evaluation, ingestion, and backtest work in asynchronous workers, not inside HTTP request handlers.
6. Keep storage and compute provider-neutral behind interfaces. Do not hardcode provider-specific assumptions in domain services.
7. PostgreSQL stores metadata and relationships. Managed object storage stores large files. GPU workers use scoped temporary access; do not assume shared storage.
8. Retain registered datasets and final model artifacts by default. Apply configurable retention to intermediate checkpoints and temporary artifacts.
9. Enforce workspace/resource authorization in backend services. Objects are private by default. Never expose permanent storage or compute credentials to clients.
10. Keep market-data/environment interfaces separate from execution/broker interfaces. Dukascopy is the first data environment; do not infer that it supports a required execution capability.
11. Do not invent API endpoints, provider features, credentials, licenses, pricing, or data guarantees. Verify provider capabilities and record limitations.
12. Use explicit schemas, type hints, migrations, structured errors, and tests. Avoid untyped dictionaries as the only contract for core entities.
13. Job status transitions, retries, idempotency, cancellation, artifact finalization, and cleanup must have defined behavior.
14. Keep model and dataset versions immutable. Experiments and backtests must reference exact input versions/configurations.
15. Never commit secrets, real credentials, private datasets, or user artifacts.
16. When changing an API contract, update schemas, tests, and documentation together.
17. For each implementation step, summarize files changed, behavior implemented, tests run, test results, unresolved limitations, and the next smallest step.
18. If a requirement is ambiguous or has a significant security/cost/provider implication, ask before making an irreversible choice.

## Expected working style

- Start by reporting repository findings and a short implementation plan.
- Make small, coherent changes.
- Add tests alongside behavior.
- Run relevant tests and report actual results; never claim tests passed unless they were run.
- Prefer real end-to-end behavior over mock-only endpoints.
