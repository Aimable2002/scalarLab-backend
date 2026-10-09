from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWKClientConnectionError, PyJWKClientError

from app.core.config import Settings
from app.core.errors import ApiError

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    user_id: UUID


def get_current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Principal:
    settings: Settings = request.app.state.settings
    jwks_client = request.app.state.jwks_client
    if settings.supabase_url is None or jwks_client is None:
        raise ApiError(503, "auth_not_configured", "Supabase Auth is not configured")
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise ApiError(401, "authentication_required", "Bearer token required")

    issuer = f"{settings.supabase_url.rstrip('/')}/auth/v1"
    try:
        header = jwt.get_unverified_header(credentials.credentials)
        algorithm = header.get("alg")
        if algorithm == "HS256":
            if settings.supabase_jwt_secret is None:
                raise InvalidTokenError("Legacy Supabase JWT secret is not configured")
            signing_key = settings.supabase_jwt_secret.get_secret_value()
            allowed_algorithms = ["HS256"]
        elif algorithm in {"ES256", "RS256"}:
            signing_key = jwks_client.get_signing_key_from_jwt(credentials.credentials).key
            allowed_algorithms = ["ES256", "RS256"]
        else:
            raise InvalidTokenError("Unsupported Supabase token signing algorithm")
        claims = jwt.decode(
            credentials.credentials,
            signing_key,
            algorithms=allowed_algorithms,
            issuer=issuer,
            audience=settings.jwt_audience,
            options={"require": ["sub", "exp", "iss", "aud"]},
        )
        user_id = UUID(claims["sub"])
    except PyJWKClientConnectionError:
        raise ApiError(
            503,
            "auth_provider_unavailable",
            "Supabase Auth keys are unavailable",
        ) from None
    except PyJWKClientError:
        raise ApiError(401, "invalid_token", "Bearer token is invalid or expired") from None
    except (InvalidTokenError, ValueError, KeyError):
        raise ApiError(401, "invalid_token", "Bearer token is invalid or expired") from None

    return Principal(user_id=user_id)