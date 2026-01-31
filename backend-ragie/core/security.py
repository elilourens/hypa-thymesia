"""JWT authentication and security utilities."""

import logging
from typing import Optional
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWKClient
from .config import settings

logger = logging.getLogger(__name__)

security = HTTPBearer()


class AuthUser:
    """Represents an authenticated user."""

    def __init__(self, sub: str, email: Optional[str] = None, token: Optional[str] = None):
        self.id = sub
        self.email = email
        self.token = token


_jwks_client = None


def _get_jwks():
    """Fetch JWK set once and reuse it."""
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(
            f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
        )
    return _jwks_client


def get_current_user(auth: HTTPAuthorizationCredentials = Depends(security)) -> AuthUser:
    """Validate JWT token and return authenticated user."""
    if auth is None:
        raise HTTPException(status_code=403, detail="No authorization header")
    token = auth.credentials
    try:
        key = _get_jwks().get_signing_key_from_jwt(token).key
        payload = jwt.decode(
            token,
            key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            options={"require": ["sub", "exp", "iat"]},
        )
    except Exception as e:
        logger.warning(f"Token validation failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return AuthUser(
        sub=payload["sub"],
        email=payload.get("email"),
        token=token
    )
