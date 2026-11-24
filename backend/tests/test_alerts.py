"""Unit and API tests for /patients/{patient_id}/alerts endpoints."""

import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from backend.app.database import Base, get_db
from backend.app.main import app
from backend.app.models import Alert, Patient


@pytest.fixture
def mock_db_session():
    """Create test session with patients and alerts."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    now = datetime.now(timezone.utc)
    p1 = Patient(id=1, participant_id="GER-001", country="GERMANY", created_at=now)
    p2 = Patient(id=2, participant_id="GER-002", country="GERMANY", created_at=now)
    session.add_all([p1, p2])
    session.commit()

    # Alerts for Patient 1: one pending, one acknowledged
    a1 = Alert(
        id=1,
        patient_id=1,
        alert_level="HIGH",
        status="pending",
        message="High exacerbation risk alert.",
        deduplication_key="dedup-1",
        created_at=now - timedelta(hours=2),
    )
    a2 = Alert(
        id=2,
        patient_id=1,
        alert_level="MEDIUM",
        status="acknowledged",
        message="Medium risk warning.",
        deduplication_key="dedup-2",
        acknowledged_at=now - timedelta(hours=1),
        created_at=now - timedelta(hours=3),
    )
    session.add_all([a1, a2])
    session.commit()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_list_alerts_all(client: TestClient, mock_db_session: Session) -> None:
    """Test retrieving all alerts for patient 1."""
    app.dependency_overrides[get_db] = lambda: mock_db_session
    try:
        response = client.get("/api/v1/patients/1/alerts")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        assert data["items"][0]["id"] == 1  # Newest first
        assert data["items"][0]["status"] == "pending"
        assert data["items"][1]["id"] == 2
        assert data["items"][1]["status"] == "acknowledged"
    finally:
        app.dependency_overrides.clear()


def test_list_alerts_filter_by_status(client: TestClient, mock_db_session: Session) -> None:
    """Test filtering alerts by status=pending."""
    app.dependency_overrides[get_db] = lambda: mock_db_session
    try:
        response = client.get("/api/v1/patients/1/alerts?status=pending")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["status"] == "pending"
    finally:
        app.dependency_overrides.clear()


def test_list_alerts_empty_patient(client: TestClient, mock_db_session: Session) -> None:
    """Test patient with no alerts returns empty items list."""
    app.dependency_overrides[get_db] = lambda: mock_db_session
    try:
        response = client.get("/api/v1/patients/2/alerts")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []
    finally:
        app.dependency_overrides.clear()


def test_list_alerts_invalid_status_422(client: TestClient, mock_db_session: Session) -> None:
    """Test invalid alert status returns 422."""
    app.dependency_overrides[get_db] = lambda: mock_db_session
    try:
        response = client.get("/api/v1/patients/1/alerts?status=invalid_status")
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_list_alerts_patient_not_found(client: TestClient, mock_db_session: Session) -> None:
    """Test nonexistent patient returns 404."""
    app.dependency_overrides[get_db] = lambda: mock_db_session
    try:
        response = client.get("/api/v1/patients/999/alerts")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
