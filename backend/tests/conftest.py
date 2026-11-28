"""Pytest test configuration and fixtures for ExacerbAlert Backend with Auth & RBAC."""

from datetime import datetime, timezone
import os
import time
from typing import Any, Dict, Generator, List, Optional
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Set testing environment before importing app
os.environ["ENVIRONMENT"] = "testing"

from backend.app.config import settings
from backend.app.core.auth import get_current_user, jwt_verifier
from backend.app.database import Base, get_db
from backend.app.main import app
from backend.app.models import Alert, ClinicianPatientAssignment, Patient, Prediction, SensorMeasurement
from backend.app.schemas.auth import AuthenticatedUser, UserRole

# Generate an isolated EC P-256 keypair for offline cryptographic testing
TEST_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
TEST_PUBLIC_KEY = TEST_PRIVATE_KEY.public_key()
TEST_KID = "test-ec-kid-01"

# Generate a secondary private key for invalid signature tests
ROGUE_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())

# Register test key in global verifier
jwt_verifier.register_test_key(TEST_KID, TEST_PUBLIC_KEY)


def make_jwt(
    sub: str = "550e8400-e29b-41d4-a716-446655440001",
    email: str = "clinician@exacerbalert.org",
    role: Optional[str] = "clinician",
    patient_ids: Optional[List[str]] = None,
    user_metadata: Optional[Dict[str, Any]] = None,
    issuer: Optional[str] = None,
    audience: Optional[str] = None,
    expires_in_seconds: int = 3600,
    kid: str = TEST_KID,
    key: Any = TEST_PRIVATE_KEY,
    algorithm: str = "ES256",
) -> str:
    """Generate cryptographically valid ES256 Supabase JWT for testing."""
    now = int(time.time())
    resolved_patient_ids = patient_ids if patient_ids is not None else ["1", "2", "3", "99999"]
    payload = {
        "sub": sub,
        "email": email,
        "aud": audience or settings.SUPABASE_JWT_AUDIENCE,
        "iss": issuer or settings.effective_jwt_issuer,
        "iat": now,
        "exp": now + expires_in_seconds,
        "app_metadata": {
            "provider": "email",
            "role": role,
            "roles": [role] if role else [],
            "patient_ids": resolved_patient_ids,
        },
        "user_metadata": user_metadata or {},
    }
    return jwt.encode(payload, key, algorithm=algorithm, headers={"kid": kid})


@pytest.fixture
def mock_db_session() -> Generator[Session, None, None]:
    """Create an isolated in-memory test database session seeded with test clinical records."""
    from sqlalchemy import text
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as conn:
        conn.execute(text("ATTACH DATABASE ':memory:' AS auth;"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS auth.users (
                id TEXT PRIMARY KEY,
                email TEXT,
                raw_app_meta_data TEXT DEFAULT '{}',
                banned_until TIMESTAMP NULL,
                deleted_at TIMESTAMP NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))
        conn.execute(text("""
            INSERT OR REPLACE INTO auth.users (id, email, raw_app_meta_data)
            VALUES ('550e8400-e29b-41d4-a716-446655440002', 'admin@exacerbalert.org', '{"role": "administrator"}');
        """))
        conn.commit()
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    now = datetime.now(timezone.utc)
    p1 = Patient(id=1, participant_id="TEST-001", country="GERMANY", created_at=now)
    p2 = Patient(id=2, participant_id="TEST-002", country="SPAIN", created_at=now)
    p3 = Patient(id=3, participant_id="TEST-003", country="GERMANY", created_at=now)
    session.add_all([p1, p2, p3])

    # Seed active assignments for default test clinician (patients 1, 2, 3)
    cpa1 = ClinicianPatientAssignment(
        clinician_id="550e8400-e29b-41d4-a716-446655440001",
        patient_id=1,
        assigned_by="550e8400-e29b-41d4-a716-446655440002",
    )
    cpa2 = ClinicianPatientAssignment(
        clinician_id="550e8400-e29b-41d4-a716-446655440001",
        patient_id=2,
        assigned_by="550e8400-e29b-41d4-a716-446655440002",
    )
    cpa3 = ClinicianPatientAssignment(
        clinician_id="550e8400-e29b-41d4-a716-446655440001",
        patient_id=3,
        assigned_by="550e8400-e29b-41d4-a716-446655440002",
    )
    # Seed active assignment for admin with patient 1
    cpa_admin = ClinicianPatientAssignment(
        clinician_id="550e8400-e29b-41d4-a716-446655440003",
        patient_id=1,
        assigned_by="550e8400-e29b-41d4-a716-446655440002",
    )
    session.add_all([cpa1, cpa2, cpa3, cpa_admin])
    session.commit()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="session")
def client() -> Generator[TestClient, None, None]:
    """Provide a TestClient instance with default authorized clinician token for existing test suite."""
    default_token = make_jwt(
        sub="550e8400-e29b-41d4-a716-446655440001",
        email="clinician.default@exacerbalert.org",
        role="clinician",
        patient_ids=["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "999", "9999", "99999"],
    )
    with TestClient(app, headers={"Authorization": f"Bearer {default_token}"}) as test_client:
        yield test_client


@pytest.fixture(scope="function")
def raw_client() -> Generator[TestClient, None, None]:
    """Provide a TestClient without default headers to verify raw HTTP auth behavior."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def clinician_token() -> str:
    """Valid JWT for clinician with access to patients 1, 2, 3."""
    return make_jwt(
        sub="550e8400-e29b-41d4-a716-446655440001",
        email="dr.smith@exacerbalert.org",
        role="clinician",
        patient_ids=["1", "2", "3"],
    )


@pytest.fixture(scope="session")
def admin_token() -> str:
    """Valid JWT for administrator without clinical patient assignments."""
    return make_jwt(
        sub="550e8400-e29b-41d4-a716-446655440002",
        email="admin@exacerbalert.org",
        role="administrator",
        patient_ids=[],
    )


@pytest.fixture(scope="session")
def admin_with_patients_token() -> str:
    """Valid JWT for administrator explicitly granted clinical access to patient 1."""
    return make_jwt(
        sub="550e8400-e29b-41d4-a716-446655440003",
        email="super.admin@exacerbalert.org",
        role="administrator",
        patient_ids=["1"],
    )


@pytest.fixture(scope="session")
def expired_token() -> str:
    """Expired JWT token (expired 1 hour ago)."""
    return make_jwt(
        sub="550e8400-e29b-41d4-a716-446655440004",
        expires_in_seconds=-3600,
    )


@pytest.fixture(scope="session")
def invalid_sig_token() -> str:
    """JWT signed with unauthorized rogue private key."""
    return make_jwt(
        sub="550e8400-e29b-41d4-a716-446655440005",
        key=ROGUE_PRIVATE_KEY,
    )
