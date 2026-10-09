from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SCALARLAB_",
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "Scalar Lab API"
    environment: str = "development"
    database_url: str | None = Field(default=None, validation_alias="SUPABASE_DATABASE_URL")
    supabase_url: str | None = Field(default=None, validation_alias="SUPABASE_URL")
    supabase_jwt_secret: SecretStr | None = Field(default=None, validation_alias="SUPABASE_JWT_SECRET")
    jwt_audience: str = "authenticated"
    object_storage_endpoint_url: str | None = Field(
        default=None, validation_alias="OBJECT_STORAGE_ENDPOINT_URL"
    )
    object_storage_bucket: str | None = Field(
        default=None, validation_alias="OBJECT_STORAGE_BUCKET"
    )
    object_storage_region: str = Field(
        default="us-east-1", validation_alias="OBJECT_STORAGE_REGION"
    )
    object_storage_access_key_id: SecretStr | None = Field(
        default=None, validation_alias="OBJECT_STORAGE_ACCESS_KEY_ID"
    )
    object_storage_secret_access_key: SecretStr | None = Field(
        default=None, validation_alias="OBJECT_STORAGE_SECRET_ACCESS_KEY"
    )
    object_storage_url_ttl_seconds: int = Field(
        default=900, ge=60, le=3600, validation_alias="OBJECT_STORAGE_URL_TTL_SECONDS"
    )
    object_storage_upload_url_ttl_seconds: int = Field(
        default=7200, ge=300, le=14400, validation_alias="OBJECT_STORAGE_UPLOAD_URL_TTL_SECONDS"
    )
    redis_url: SecretStr | None = Field(default=None, validation_alias="REDIS_URL")
    modal_app_name: str | None = Field(default=None, validation_alias="MODAL_APP_NAME")
    modal_function_name: str | None = Field(default=None, validation_alias="MODAL_FUNCTION_NAME")

    @field_validator("database_url")
    @classmethod
    def require_supabase_postgres_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError("SUPABASE_DATABASE_URL must be a PostgreSQL connection URL")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()