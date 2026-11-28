"""Unit and API tests for /patients endpoints."""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from backend.app.database import Base, get_db
from backend.app.main import app
from backend.app.models import ClinicianPatientAssignment, Patient


@pytest.fixture
def mock_db_session():
    """Create an isolated in-memory test database session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    # Seed 3 mock patients for testing
    now = datetime.now(timezone.utc)
    p1 = Patient(id=1, participant_id="TEST-001", country="GERMANY", created_at=now)
    p2 = Patient(id=2, participant_id="TEST-002", country="SPAIN", created_at=now)
    p3 = Patient(id=3, participant_id="TEST-003", country="GERMANY", created_at=now)
    session.add_all([p1, p2, p3])

    # Seed active assignments for default client clinician (including 9999 for 404 test)
    for pid in (1, 2, 3, 9999):
        session.add(
            ClinicianPatientAssignment(
                clinician_id="550e8400-e29b-41d4-a716-446655440001",
                patient_id=pid,
                assigned_by="550e8400-e29b-41d4-a716-446655440002",
            )
        )
    session.commit()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_list_patients_success(client: TestClient, mock_db_session: Session) -> None:
    """Test GET /api/v1/patients returns paginated list."""
    app.dependency_overrides[get_db] = lambda: mock_db_session
    try:
        response = client.get("/api/v1/patients?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert data["total"] == 3
        assert data["limit"] == 2
        assert data["offset"] == 0
        assert len(data["items"]) == 2
        assert data["items"][0]["participant_id"] == "TEST-001"
        assert data["items"][1]["participant_id"] == "TEST-002"
    finally:
        app.dependency_overrides.clear()


def test_list_patients_country_filter(client: TestClient, mock_db_session: Session) -> None:
    """Test filtering patients by country."""
    app.dependency_overrides[get_db] = lambda: mock_db_session
    try:
        response = client.get("/api/v1/patients?country=SPAIN")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["participant_id"] == "TEST-002"
    finally:
        app.dependency_overrides.clear()


def test_get_patient_by_id_success(client: TestClient, mock_db_session: Session) -> None:
    """Test GET /api/v1/patients/{id} returns single patient."""
    app.dependency_overrides[get_db] = lambda: mock_db_session
    try:
        response = client.get("/api/v1/patients/1")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["participant_id"] == "TEST-001"
        assert data["country"] == "GERMANY"
        # Verify unverified columns were not invented
        assert "status" not in data
        assert "kit_id" not in data
    finally:
        app.dependency_overrides.clear()


def test_get_patient_by_id_not_found(client: TestClient, mock_db_session: Session) -> None:
    """Test GET /api/v1/patients/{id} returns 404 for missing patient."""
    app.dependency_overrides[get_db] = lambda: mock_db_session
    try:
        response = client.get("/api/v1/patients/9999")
        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "HTTP_404"
        assert "9999" in data["error"]["message"]
    finally:
        app.dependency_overrides.clear()
