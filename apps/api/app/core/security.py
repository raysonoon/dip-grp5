from functools import lru_cache

import jwt
from fastapi import HTTPException, status
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError
from pwdlib import PasswordHash

from app.core.config import settings

password_hash = PasswordHash.recommended()

ALLOWED_ALGORITHMS = ["ES256", "RS256"]


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


@lru_cache(maxsize=1)
def _get_jwks_client() -> PyJWKClient:
    if not settings.supabase_jwks_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase authentication is not configured",
        )
    return PyJWKClient(settings.supabase_jwks_url)

def verify_supabase_access_token(token: str) -> dict[str, object]:
    """Verify a Supabase access token and return its trusted claims."""
    if not settings.supabase_jwt_issuer:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase authentication is not configured",
        )

    # Guard against a "Bearer " prefix accidentally being passed in.
    if token.lower().startswith("bearer "):
        token = token[7:].strip()

    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=ALLOWED_ALGORITHMS,
            audience=settings.supabase_jwt_audience,
            issuer=settings.supabase_jwt_issuer,
            leeway=10,  # tolerate small clock skew
        )
        return claims

    except PyJWKClientConnectionError as error:
        # Could not reach the JWKS endpoint: server-side problem, not a bad token.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication provider unreachable",
        ) from error

    except jwt.ExpiredSignatureError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    except jwt.PyJWTError as error:
        # Covers InvalidAudienceError, InvalidIssuerError, InvalidAlgorithmError,
        # InvalidSignatureError, PyJWKClientError (e.g. kid not found), DecodeError...
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Supabase access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    except OSError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication provider unreachable",
        ) from error