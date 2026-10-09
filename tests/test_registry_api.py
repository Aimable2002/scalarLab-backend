from datetime import UTC, datetime, timedelta
import os
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.base import Base
from app.main import create_app

TEST_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
TEST_PUBLIC_KEY = TEST_PRIVATE_KEY.public_key()


class StaticJwksClient:
    def get_signing_key_from_jwt(self, token):
        return SimpleNamespace(key=TEST_PUBLIC_KEY)


def make_app():
    database_url = os.getenv("SUPABASE_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set SUPABASE_TEST_DATABASE_URL to a dedicated Supabase test database")
    app = create_app(
        Settings(
            database_url=database_url,
            supabase_url="https://scalar-lab.supabase.co",
        )
    )
    app.state.jwks_client = StaticJwksClient()
    assert app.state.engine is not None
    Base.metadata.create_all(app.state.engine)
    return app


def bearer(user_id=None):
    claims = {
        "sub": str(user_id or uuid4()),
        "iss": "https://scalar-lab.supabase.co/auth/v1",
        "aud": "authenticated",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    return {"Authorization": f"Bearer {jwt.encode(claims, TEST_PRIVATE_KEY, algorithm='RS256')}"}


def create_workspace(client, headers):
    response = client.post("/api/v1/workspaces", json={"name": "Research"}, headers=headers)
    assert response.status_code == 201
    return response.json()["id"]


def test_registry_requires_bearer_authentication():
    app = make_app()
    with TestClient(app) as client:
        response = client.get("/api/v1/workspaces")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]


def test_external_dataset_registration_is_workspace_scoped_and_rejects_files():
    app = make_app()
    owner_headers = bearer()
    with TestClient(app) as client:
        workspace_id = create_workspace(client, owner_headers)
        payload = {
            "name": "EURUSD hourly bars",
            "provider": "huggingface",
            "source_id": "research/eurusd-bars",
            "revision": "a" * 40,
            "file_path": "eurusd/hourly.csv",
            "license_name": "CC-BY-4.0",
            "schema_summary": {"columns": ["timestamp", "close"]},
        }
        registered = client.post(
            f"/api/v1/workspaces/{workspace_id}/datasets",
            json=payload,
            headers=owner_headers,
        )
        assert registered.status_code == 201
        body = registered.json()
        assert body["provider"] == "huggingface"
        assert body["source_id"] == "research/eurusd-bars"
        assert body["versions"][0]["revision"] == "a" * 40
        assert body["versions"][0]["file_path"] == "eurusd/hourly.csv"
        assert body["versions"][0]["status"] == "registered"
        assert "artifact_ref" not in body["versions"][0]

        with_file_payload = client.post(
            f"/api/v1/workspaces/{workspace_id}/datasets",
            json={**payload, "name": "Should reject", "source_id": "other/data", "file": "bytes"},
            headers=owner_headers,
        )
        assert with_file_payload.status_code == 422
        assert with_file_payload.json()["error"]["code"] == "validation_error"

        private_response = client.get(
            f"/api/v1/workspaces/{workspace_id}/datasets",
            headers=bearer(),
        )
        assert private_response.status_code == 404
        assert private_response.json()["error"]["code"] == "workspace_not_found"


def test_dataset_revisions_are_immutable():
    app = make_app()
    headers = bearer()
    with TestClient(app) as client:
        workspace_id = create_workspace(client, headers)
        payload = {
            "name": "FX dataset",
            "provider": "kaggle",
            "source_id": "author/fx-data",
            "revision": "v1",
        }
        created = client.post(
            f"/api/v1/workspaces/{workspace_id}/datasets", json=payload, headers=headers
        )
        dataset_id = created.json()["id"]

        duplicate = client.post(
            f"/api/v1/workspaces/{workspace_id}/datasets/{dataset_id}/versions",
            json={"revision": "v1"},
            headers=headers,
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "dataset_revision_exists"

        next_version = client.post(
            f"/api/v1/workspaces/{workspace_id}/datasets/{dataset_id}/versions",
            json={"revision": "v2"},
            headers=headers,
        )
        assert next_version.status_code == 201
        assert [version["revision"] for version in next_version.json()["versions"]] == ["v1", "v2"]


def test_model_reference_can_be_registered_and_listed():
    app = make_app()
    headers = bearer()
    with TestClient(app) as client:
        workspace_id = create_workspace(client, headers)
        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/models",
            json={
                "name": "Baseline transformer",
                "source_type": "huggingface",
                "source_id": "org/model",
                "revision": "commit-123",
                "source_uri": "https://huggingface.co/org/model",
            },
            headers=headers,
        )
        assert response.status_code == 201
        assert response.json()["versions"][0]["revision"] == "commit-123"

        listed = client.get(f"/api/v1/workspaces/{workspace_id}/models", headers=headers)
        assert listed.status_code == 200
        assert len(listed.json()) == 1