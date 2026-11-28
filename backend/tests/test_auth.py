"""Unit and integration tests for Supabase JWT verification and authentication security."""

import time
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import status
from fastapi.testclient import TestClient

from backend.app.config import settings
from backend.app.core.auth import jwt_verifier
from backend.tests.conftest import (
    ROGUE_PRIVATE_KEY,
    TEST_KID,
    TEST_PRIVATE_KEY,
    make_jwt,
)


def test_public_health_endpoint_accessible_without_jwt(raw_client: TestClient):
    """Verify infrastructure /health endpoint remains accessible without credentials."""
    response = raw_client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    assert "status" in response.json()

    api_response = raw_client.get("/api/v1/health")
    assert api_response.status_code == status.HTTP_200_OK


def test_missing_jwt_returns_401(raw_client: TestClient):
    """Verify protected clinical endpoint rejects unauthenticated request with 401."""
    response = raw_client.get("/api/v1/patients")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "WWW-Authenticate" in response.headers
    data = response.json()
    assert "error" in data
    assert "Authentication required" in data["error"]["message"]


def test_malformed_jwt_returns_401(raw_client: TestClient):
    """Verify malformed bearer token returns 401."""
    response = raw_client.get(
        "/api/v1/patients",
        headers={"Authorization": "Bearer this-is-not-a-valid-jwt-token"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Malformed token header" in response.json()["error"]["message"]


def test_expired_jwt_returns_401(raw_client: TestClient, expired_token: str):
    """Verify expired token returns 401 with appropriate error description."""
    response = raw_client.get(
        "/api/v1/patients",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "expired" in response.json()["error"]["message"].lower()


def test_invalid_jwt_signature_returns_401(raw_client: TestClient, invalid_sig_token: str):
    """Verify token signed with rogue key fails cryptographic signature verification with 401."""
    response = raw_client.get(
        "/api/v1/patients",
        headers={"Authorization": f"Bearer {invalid_sig_token}"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "signature" in response.json()["error"]["message"].lower()


def test_invalid_issuer_returns_401(raw_client: TestClient):
    """Verify token from untrusted issuer is rejected with 401."""
    token = make_jwt(issuer="https://malicious-issuer.com/auth/v1")
    response = raw_client.get(
        "/api/v1/patients",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "issuer" in response.json()["error"]["message"].lower()


def test_invalid_audience_returns_401(raw_client: TestClient):
    """Verify token with wrong audience is rejected with 401."""
    token = make_jwt(audience="wrong-audience")
    response = raw_client.get(
        "/api/v1/patients",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "audience" in response.json()["error"]["message"].lower()


def test_unsupported_signing_algorithm_returns_401(raw_client: TestClient):
    """Verify symmetric 'HS256' or unpermitted algorithms are rejected with 401."""
    # Create token with unsupported algorithm header
    import jwt
    token = jwt.encode(
        {"sub": "123", "exp": int(time.time()) + 3600, "aud": settings.SUPABASE_JWT_AUDIENCE, "iss": settings.effective_jwt_issuer},
        "secret",
        algorithm="HS256",
        headers={"kid": "hs256-kid"},
    )
    response = raw_client.get(
        "/api/v1/patients",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Unsupported signing algorithm" in response.json()["error"]["message"]


def test_none_algorithm_rejected_with_401(raw_client: TestClient):
    """Verify unsigned 'none' algorithm tokens are strictly rejected with 401."""
    import base64
    import json
    header_b64 = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).decode().rstrip("=")
    payload_b64 = base64.urlsafe_b64encode(json.dumps({
        "sub": "123",
        "exp": int(time.time()) + 3600,
        "aud": settings.SUPABASE_JWT_AUDIENCE,
        "iss": settings.effective_jwt_issuer,
    }).encode()).decode().rstrip("=")
    unsigned_none_token = f"{header_b64}.{payload_b64}."

    response = raw_client.get(
        "/api/v1/patients",
        headers={"Authorization": f"Bearer {unsigned_none_token}"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Unsupported signing algorithm 'none'" in response.json()["error"]["message"]


def test_role_in_client_user_metadata_is_ignored(raw_client: TestClient):
    """CRITICAL SECURITY TEST: Ensure role claimed in client-editable user_metadata is ignored."""
    # Token has NO role in app_metadata, but claims 'administrator' in user_metadata
    spoofed_token = make_jwt(
        role=None,
        user_metadata={"role": "administrator", "roles": ["administrator"]},
    )
    # /admin/users requires administrator role
    response = raw_client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {spoofed_token}"},
    )
    # Must be 403 Forbidden because user_metadata is never trusted
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_key_rotation_support(raw_client: TestClient):
    """Verify dynamic key rotation: verifier resolves newly rotated keys by kid."""
    rotated_private_key = ec.generate_private_key(ec.SECP256R1())
    rotated_public_key = rotated_private_key.public_key()
    rotated_kid = "rotated-ec-kid-99"

    # Register the newly rotated key
    jwt_verifier.register_test_key(rotated_kid, rotated_public_key)

    token = make_jwt(
        kid=rotated_kid,
        key=rotated_private_key,
        role="clinician",
        patient_ids=["1"],
    )
    response = raw_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["role"] == "clinician"


def test_direct_token_endpoint_disabled_in_production(raw_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """SECURITY TEST: Direct token issuance endpoint must return 403 outside dev/test environments."""
    from backend.app.api.routes import auth
    monkeypatch.setattr(auth.settings, "ENVIRONMENT", "production")
    response = raw_client.post(
        "/api/v1/auth/token",
        json={"email": "attacker@evil.com", "role": "administrator"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    data = response.json()
    msg = data.get("error", {}).get("message") or data.get("detail", "")
    assert "Direct token issuance endpoint is disabled" in msg


def test_demo_secret_token_rejected_by_live_endpoints(raw_client: TestClient):
    """SECURITY TEST: Demo-mode secret strings must never be accepted as valid bearer tokens."""
    response = raw_client.get(
        "/api/v1/patients",
        headers={"Authorization": "Bearer demo-clinician-secret"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_token_within_max_jwt_lifetime_accepted(raw_client: TestClient):
    """Verify token with lifespan <= MAX_JWT_LIFETIME_SECONDS is cryptographically accepted."""
    token = make_jwt(
        sub="550e8400-e29b-41d4-a716-446655440001",
        role="clinician",
        expires_in_seconds=settings.MAX_JWT_LIFETIME_SECONDS,
    )
    response = raw_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == status.HTTP_200_OK


def test_token_exceeding_max_jwt_lifetime_rejected(raw_client: TestClient):
    """SECURITY TEST: Token with lifespan (exp - iat) exceeding MAX_JWT_LIFETIME_SECONDS is rejected."""
    excessive_duration = settings.MAX_JWT_LIFETIME_SECONDS + 600
    token = make_jwt(
        sub="550e8400-e29b-41d4-a716-446655440001",
        role="clinician",
        expires_in_seconds=excessive_duration,
    )
    response = raw_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    data = response.json()
    msg = data.get("error", {}).get("message") or data.get("detail", "")
    assert "exceeds maximum allowed duration" in msg


def test_token_missing_iat_rejected(raw_client: TestClient):
    """SECURITY TEST: Token missing 'iat' (issued at) claim is rejected with HTTP 401."""
    import jwt
    now = int(time.time())
    payload = {
        "sub": "550e8400-e29b-41d4-a716-446655440001",
        "email": "clinician@exacerbalert.org",
        "aud": settings.SUPABASE_JWT_AUDIENCE,
        "iss": settings.effective_jwt_issuer,
        # 'iat' deliberately omitted
        "exp": now + 1800,
        "app_metadata": {
            "provider": "email",
            "role": "clinician",
            "roles": ["clinician"],
            "patient_ids": ["1"],
        },
        "user_metadata": {},
    }
    token = jwt.encode(payload, TEST_PRIVATE_KEY, algorithm="ES256", headers={"kid": TEST_KID})
    response = raw_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    data = response.json()
    msg = data.get("error", {}).get("message") or data.get("detail", "")
    assert "iat" in msg.lower() or "missing" in msg.lower()


def test_token_future_iat_rejected(raw_client: TestClient):
    """SECURITY TEST: Token with 'iat' claim in the future is rejected with HTTP 401."""
    import jwt
    now = int(time.time())
    payload = {
        "sub": "550e8400-e29b-41d4-a716-446655440001",
        "email": "clinician@exacerbalert.org",
        "aud": settings.SUPABASE_JWT_AUDIENCE,
        "iss": settings.effective_jwt_issuer,
        "iat": now + 600,  # 10 minutes in the future
        "exp": now + 3600,
        "app_metadata": {
            "provider": "email",
            "role": "clinician",
            "roles": ["clinician"],
            "patient_ids": ["1"],
        },
        "user_metadata": {},
    }
    token = jwt.encode(payload, TEST_PRIVATE_KEY, algorithm="ES256", headers={"kid": TEST_KID})
    response = raw_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    data = response.json()
    msg = data.get("error", {}).get("message") or data.get("detail", "")
    assert "future" in msg.lower() or "not yet valid" in msg.lower() or "iat" in msg.lower()


def test_token_exp_equal_or_before_iat_rejected(raw_client: TestClient):
    """SECURITY TEST: Token with exp <= iat is rejected with HTTP 401."""
    import jwt
    now = int(time.time())
    payload = {
        "sub": "550e8400-e29b-41d4-a716-446655440001",
        "email": "clinician@exacerbalert.org",
        "aud": settings.SUPABASE_JWT_AUDIENCE,
        "iss": settings.effective_jwt_issuer,
        "iat": now,
        "exp": now,  # exp == iat
        "app_metadata": {
            "provider": "email",
            "role": "clinician",
            "roles": ["clinician"],
            "patient_ids": ["1"],
        },
        "user_metadata": {},
    }
    token = jwt.encode(payload, TEST_PRIVATE_KEY, algorithm="ES256", headers={"kid": TEST_KID})
    response = raw_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    data = response.json()
    msg = data.get("error", {}).get("message") or data.get("detail", "")
    assert "exp" in msg.lower() or "later" in msg.lower() or "expired" in msg.lower()


def test_token_missing_exp_rejected(raw_client: TestClient):
    """SECURITY TEST: Token missing 'exp' (expiration) claim is rejected with HTTP 401."""
    import jwt
    now = int(time.time())
    payload = {
        "sub": "550e8400-e29b-41d4-a716-446655440001",
        "email": "clinician@exacerbalert.org",
        "aud": settings.SUPABASE_JWT_AUDIENCE,
        "iss": settings.effective_jwt_issuer,
        "iat": now,
        # 'exp' deliberately omitted
        "app_metadata": {
            "provider": "email",
            "role": "clinician",
            "roles": ["clinician"],
            "patient_ids": ["1"],
        },
        "user_metadata": {},
    }
    token = jwt.encode(payload, TEST_PRIVATE_KEY, algorithm="ES256", headers={"kid": TEST_KID})
    response = raw_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    data = response.json()
    msg = data.get("error", {}).get("message") or data.get("detail", "")
    assert "exp" in msg.lower() or "missing" in msg.lower()


def test_token_malformed_claim_types_rejected(raw_client: TestClient):
    """SECURITY TEST: Token with non-numeric temporal claims consistently returns HTTP 401, not 500."""
    import jwt
    now = int(time.time())

    # Case 1: string iat
    p1 = {
        "sub": "550e8400-e29b-41d4-a716-446655440001",
        "email": "clinician@exacerbalert.org",
        "aud": settings.SUPABASE_JWT_AUDIENCE,
        "iss": settings.effective_jwt_issuer,
        "iat": "invalid-non-numeric-timestamp",
        "exp": now + 3600,
        "app_metadata": {"role": "clinician"},
    }
    t1 = jwt.encode(p1, TEST_PRIVATE_KEY, algorithm="ES256", headers={"kid": TEST_KID})
    r1 = raw_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {t1}"})
    assert r1.status_code == status.HTTP_401_UNAUTHORIZED

    # Case 2: string exp
    p2 = {
        "sub": "550e8400-e29b-41d4-a716-446655440001",
        "email": "clinician@exacerbalert.org",
        "aud": settings.SUPABASE_JWT_AUDIENCE,
        "iss": settings.effective_jwt_issuer,
        "iat": now,
        "exp": "never-expire",
        "app_metadata": {"role": "clinician"},
    }
    t2 = jwt.encode(p2, TEST_PRIVATE_KEY, algorithm="ES256", headers={"kid": TEST_KID})
    r2 = raw_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {t2}"})
    assert r2.status_code == status.HTTP_401_UNAUTHORIZED

