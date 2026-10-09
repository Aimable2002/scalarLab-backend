from collections.abc import Generator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from jwt import PyJWKClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings, get_settings
from app.core.errors import ApiError, handle_api_error, handle_validation_error
from app.api.routes import router
from app.adapters.storage.s3 import S3CompatibleStorage
from app.adapters.compute.modal import ModalComputeAdapter
from app.adapters.queue.celery import CeleryJobQueue


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    engine = (
        create_engine(app_settings.database_url, pool_pre_ping=True)
        if app_settings.database_url is not None
        else None
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> Generator[None, None, None]:
        application.state.engine = engine
        yield
        if engine is not None:
            engine.dispose()

    application = FastAPI(
        title=app_settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.engine = engine
    application.state.settings = app_settings
    application.state.object_storage = (
        S3CompatibleStorage.from_settings(app_settings)
        if app_settings.object_storage_bucket is not None
        else None
    )
    application.state.compute_provider = (
        ModalComputeAdapter.from_settings(app_settings)
        if app_settings.modal_app_name is not None or app_settings.modal_function_name is not None
        else None
    )
    application.state.job_queue = (
        CeleryJobQueue.from_settings(app_settings)
        if app_settings.redis_url is not None
        else None
    )
    application.state.jwks_client = (
        PyJWKClient(
            f"{app_settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        )
        if app_settings.supabase_url is not None
        else None
    )
    application.include_router(router)
    application.add_exception_handler(ApiError, handle_api_error)
    application.add_exception_handler(RequestValidationError, handle_validation_error)

    @application.middleware("http")
    async def add_request_id(request: Request, call_next) -> Response:
        request_id = str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @application.get("/health/live", tags=["health"])
    def liveness() -> dict[str, str]:
        return {"status": "alive"}

    @application.get("/health/ready", tags=["health"])
    def readiness(request: Request, response: Response) -> dict[str, str]:
        db_engine: Engine | None = request.app.state.engine
        if db_engine is None:
            response.status_code = 503
            return {"status": "not_ready", "database": "not_configured"}
        try:
            with db_engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            response.status_code = 503
            return {"status": "not_ready", "database": "unavailable"}
        return {"status": "ready", "database": "available"}

    return application


app = create_app()