import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_supabase_database_url_is_loaded(monkeypatch):
    monkeypatch.setenv(
        "SUPABASE_DATABASE_URL",
        "postgresql+psycopg://user:pass@supabase.example:5432/postgres",
    )

    settings = Settings(_env_file=None)

    assert settings.database_url == "postgresql+psycopg://user:pass@supabase.example:5432/postgres"


@pytest.mark.parametrize(
    "supabase_url",
    [
        "postgresql://user:pass@supabase.example:5432/postgres",
        "postgres://user:pass@supabase.example:5432/postgres",
    ],
)
def test_standard_supabase_postgres_urls_use_psycopg3(supabase_url):
    settings = Settings(database_url=supabase_url, _env_file=None)

    assert settings.database_url == "postgresql+psycopg://user:pass@supabase.example:5432/postgres"


def test_database_url_is_unconfigured_when_supabase_url_is_missing(monkeypatch):
    monkeypatch.delenv("SUPABASE_DATABASE_URL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.database_url is None


def test_non_supabase_database_url_is_rejected():
    with pytest.raises(ValidationError):
        Settings(database_url="mysql://user:pass@db.example/database", _env_file=None)