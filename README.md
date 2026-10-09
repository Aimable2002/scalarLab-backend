# Scalar Lab Backend

Initial FastAPI backend foundation for the documented V1 architecture.

## Local setup

Use Python 3.12 or newer and a Supabase project. Copy `.env.example` to `.env`, set `SUPABASE_DATABASE_URL` to the SQLAlchemy-compatible connection string from the Supabase dashboard, and set `SUPABASE_URL` to the project URL. The database URL is required for database operations; the application has no local database fallback. The database uses Supabase's managed PostgreSQL service through SQLAlchemy/psycopg. API access tokens are verified against the Supabase Auth project JWKS for asymmetric signing keys, with issuer and `authenticated` audience validation. Only legacy HS256 projects need `SUPABASE_JWT_SECRET`; keep it server-side. Keep all Supabase connection details server-side.

Artifact storage uses a private S3-compatible bucket. Configure the bucket, region, endpoint, and server-side access credentials with the `OBJECT_STORAGE_*` variables in `.env.example`. Omit the endpoint when using AWS S3. Presigned URLs are short-lived; never expose permanent storage credentials to the frontend.

Modal is the first compute adapter. Set `MODAL_APP_NAME`, `MODAL_FUNCTION_NAME`, and `MODAL_GPU_TYPE` before deploying `modal_app.py`; this explicit GPU selection avoids silently choosing a cost tier. Create the Modal secret named by `MODAL_WORKER_SECRET_NAME` with `HF_TOKEN` for private Hugging Face datasets, then configure `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` for the backend worker through its secret manager. The Modal function downloads a pinned Hugging Face dataset revision into temporary storage, runs the OHLCV baseline, uploads final weights through the short-lived S3 authorization, and cleans its temporary data. Kaggle dataset references can be registered, but runs using them are rejected until a verifiable pinned-revision download API is available.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
alembic upgrade head
uvicorn app.main:app --reload
```

Run a separate worker process with the same Supabase, Redis, object-storage, and Modal configuration:

```bash
celery -A app.worker.celery_app:celery_app worker --loglevel=INFO
```

`REDIS_URL` must point to the selected Redis service; no local broker/database fallback is created.

Deploy the GPU function separately after setting `MODAL_GPU_TYPE` and authenticating the Modal CLI:

```bash
modal deploy modal_app.py
```

`GET /health/live` reports process liveness. `GET /health/ready` checks the configured database. OpenAPI is available at `/docs` while the service is running.

## Current API slice

All registry operations require a valid bearer token and are scoped to workspace membership:

- `POST /api/v1/workspaces` and `GET /api/v1/workspaces`
- `POST /api/v1/workspaces/{workspace_id}/datasets` and `GET /api/v1/workspaces/{workspace_id}/datasets`
- `POST /api/v1/workspaces/{workspace_id}/datasets/{dataset_id}/versions`
- `POST /api/v1/workspaces/{workspace_id}/models` and `GET /api/v1/workspaces/{workspace_id}/models`
- `POST /api/v1/workspaces/{workspace_id}/models/{model_id}/versions`
- `POST /api/v1/workspaces/{workspace_id}/experiments` and `GET /api/v1/workspaces/{workspace_id}/experiments`
- `POST /api/v1/workspaces/{workspace_id}/experiments/{experiment_id}/runs`
- `GET /api/v1/workspaces/{workspace_id}/jobs/{job_id}`
- `POST /api/v1/workspaces/{workspace_id}/jobs/{job_id}/cancel`
- `GET /api/v1/workspaces/{workspace_id}/jobs/{job_id}/logs`
- `POST /api/v1/workspaces/{workspace_id}/artifacts/upload-authorizations`
- `POST /api/v1/workspaces/{workspace_id}/artifacts/{artifact_id}/finalize`
- `POST /api/v1/workspaces/{workspace_id}/artifacts/{artifact_id}/download-authorization`

Dataset endpoints register Kaggle or Hugging Face references and metadata only. They reject unknown fields, including dataset file payloads. Runs currently support only pinned Hugging Face revisions; Kaggle references can be registered but are rejected for execution until immutable revision downloads are verified.

This is an initial vertical slice, not the complete platform. Artifact uploads are workspace-scoped and finalized after object metadata is verified. Successful Forex baseline runs publish a model version linked to its final S3 artifact. GPU deployment requires a separately deployed Modal function, Modal credentials, a configured private S3 bucket, Supabase project, and Redis service. Automatic retries, job progress percentages, and recovery of workers lost mid-run remain future work.

## Checks

```bash
python -m pytest
```

Registry integration tests require `SUPABASE_TEST_DATABASE_URL` to point to a dedicated, disposable Supabase test project. They skip when this variable is not set; never point it at production.