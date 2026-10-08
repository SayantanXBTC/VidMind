"""Request authentication with Supabase Auth.

The frontend signs users in with Supabase and sends the session's access
token (a JWT) as `Authorization: Bearer <token>`. We verify it locally:
newer Supabase projects sign tokens with asymmetric keys published at the
project's JWKS endpoint; older ones use a shared HS256 secret
(SUPABASE_JWT_SECRET).

With SUPABASE_URL unset, auth is off and every request acts as the "local"
user, so the app still runs as a single-user tool on one machine.
"""
import logging
from dataclasses import dataclass
from typing import Optional

import jwt
from fastapi import HTTPException, Query, Request, status

from app.core.config import settings

logger = logging.getLogger(__name__)

LOCAL_USER_ID = "local"

_jwks_client: Optional[jwt.PyJWKClient] = None


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: Optional[str] = None


def _get_jwks_client() -> jwt.PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(
            f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json",
            cache_keys=True,
            lifespan=3600,
        )
    return _jwks_client


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def verify_token(token: str) -> CurrentUser:
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") == "HS256":
            if not settings.SUPABASE_JWT_SECRET:
                raise _unauthorized("Server is missing SUPABASE_JWT_SECRET for HS256 tokens")
            key = settings.SUPABASE_JWT_SECRET
            algorithms = ["HS256"]
        else:
            key = _get_jwks_client().get_signing_key_from_jwt(token).key
            algorithms = ["ES256", "RS256", "EdDSA"]
        claims = jwt.decode(
            token,
            key,
            algorithms=algorithms,
            audience="authenticated",
            issuer=f"{settings.SUPABASE_URL}/auth/v1",
        )
    except HTTPException:
        raise
    except jwt.ExpiredSignatureError as exc:
        raise _unauthorized("Your session expired. Sign in again.") from exc
    except (jwt.PyJWTError, jwt.PyJWKClientError) as exc:
        logger.info("Rejected token: %s", exc)
        raise _unauthorized("Invalid sign-in token") from exc

    user_id = claims.get("sub")
    if not user_id:
        raise _unauthorized("Invalid sign-in token")
    return CurrentUser(id=user_id, email=claims.get("email"))


def get_current_user(
    request: Request,
    access_token: Optional[str] = Query(default=None, include_in_schema=False),
) -> CurrentUser:
    """FastAPI dependency. `access_token` as a query parameter exists for
    <video src> requests, which can't send an Authorization header."""
    if not settings.AUTH_ENABLED:
        return CurrentUser(id=LOCAL_USER_ID)

    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else access_token
    if not token:
        raise _unauthorized("Sign in to use VidMind")
    return verify_token(token)
