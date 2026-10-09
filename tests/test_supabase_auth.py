from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import SecretStr

from app.core.config import Settings
from app.core.errors import ApiError
from app.core.security import get_current_principal


class StaticJwksClient:
    def __init__(self, public_key):
        self.public_key = public_key

    def get_signing_key_from_jwt(self, token):
        return SimpleNamespace(key=self.public_key)


@pytest.fixture
def signing_keys():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def make_request(public_key, jwt_secret=None):
    settings = Settings(
        supabase_url="https://scalar-lab.supabase.co",
        supabase_jwt_secret=SecretStr(jwt_secret) if jwt_secret else None,
        _env_file=None,
    )
    state = SimpleNamespace(settings=settings, jwks_client=StaticJwksClient(public_key))
    return SimpleNamespace(app=SimpleNamespace(state=state))


def make_token(private_key, issuer, subject=None):
    claims = {
        "sub": str(subject or uuid4()),
        "iss": issuer,
        "aud": "authenticated",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    return jwt.encode(claims, private_key, algorithm="RS256")


def test_supabase_auth_token_is_verified_and_resolves_user(signing_keys):
    private_key, public_key = signing_keys
    subject = uuid4()
    token = make_token(private_key, "https://scalar-lab.supabase.co/auth/v1", subject)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    principal = get_current_principal(make_request(public_key), credentials)

    assert principal.user_id == subject


def test_token_with_wrong_supabase_issuer_is_rejected(signing_keys):
    private_key, public_key = signing_keys
    token = make_token(private_key, "https://other-project.supabase.co/auth/v1")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(ApiError) as error:
        get_current_principal(make_request(public_key), credentials)

    assert error.value.code == "invalid_token"


def test_legacy_supabase_hs256_token_requires_configured_project_secret():
    jwt_secret = "legacy-supabase-jwt-secret-value"
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "iss": "https://scalar-lab.supabase.co/auth/v1",
            "aud": "authenticated",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        jwt_secret,
        algorithm="HS256",
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(ApiError) as error:
        get_current_principal(make_request(None), credentials)
    assert error.value.code == "invalid_token"

    principal = get_current_principal(make_request(None, jwt_secret), credentials)

    assert principal.user_id