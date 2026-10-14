from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException

from app.core import security
from app.core.config import settings


@pytest.fixture
def es256_token(monkeypatch: pytest.MonkeyPatch) -> tuple[str, object]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    class FakeJwksClient:
        def get_signing_key_from_jwt(self, token: str) -> SimpleNamespace:
            return SimpleNamespace(key=public_key)

    monkeypatch.setattr(
        security,
        "_get_jwks_client",
        lambda: FakeJwksClient(),
    )
    monkeypatch.setattr(
        settings,
        "supabase_jwt_issuer",
        "https://example.supabase.co/auth/v1",
    )
    monkeypatch.setattr(settings, "supabase_jwt_audience", "authenticated")
    token = jwt.encode(
            {
                "sub": "user-id",
                "email": "user@example.com",
                "iss": settings.supabase_jwt_issuer,
                "aud": settings.supabase_jwt_audience,
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            private_key,
            algorithm="ES256",
        )
    return token, private_key


def test_verify_supabase_access_token_accepts_es256(es256_token: str) -> None:
    token, _ = es256_token
    claims = security.verify_supabase_access_token(token)

    assert claims["sub"] == "user-id"
    assert claims["email"] == "user@example.com"


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("iss", "https://wrong.example.com/auth/v1"),
        ("aud", "wrong-audience"),
    ],
)
def test_verify_supabase_access_token_rejects_wrong_claims(
    es256_token: tuple[str, object],
    claim: str,
    value: str,
) -> None:
    token, private_key = es256_token
    decoded = jwt.decode(token, options={"verify_signature": False})
    decoded[claim] = value

    with pytest.raises(HTTPException) as error:
        security.verify_supabase_access_token(
            jwt.encode(decoded, private_key, algorithm="ES256")
        )

    assert error.value.status_code == 401