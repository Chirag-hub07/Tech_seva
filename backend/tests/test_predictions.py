"""Unit and API tests for /patients/{patient_id}/predictions endpoints."""

import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from backend.app.database import Base, get_db
from backend.app.main import app
from backend.app.models import Patient, Prediction


@pytest.fixture
def mock_db_session():
    """Create isolated test session with patients and predictions."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    now = datetime.now(timezone.utc)
    # Patient 1 has 2 predictions
    p1 = Patient(id=1, participant_id="GER-001", country="GERMANY", created_at=now)
    # Patient 2 has NO predictions
    p2 = Patient(id=2, participant_id="GER-002", country="GERMANY", created_at=now)
    session.add_all([p1, p2])
    session.commit()

    pred_old = Prediction(
        id=1,
        patient_id=1,
        prediction_timestamp=now - timedelta(days=2),
        risk_probability=0.25,
        risk_level="LOW",
        prediction_horizon_days=7,
        model_version="v1.0",
        created_at=now - timedelta(days=2),
    )
    pred_new = Prediction(
        id=2,
        patient_id=1,
        prediction_timestamp=now,
        risk_probability=0.72,
        risk_level="HIGH",
        prediction_horizon_days=7,
        model_version="v1.1",
        created_at=now,
    )
    session.add_all([pred_old, pred_new])
    session.commit()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_latest_prediction_exists(client: TestClient, mock_db_session: Session) -> None:
    """Test retrieving latest prediction returns newest record (pred_new)."""
    app.dependency_overrides[get_db] = lambda: mock_db_session
    try:
        response = client.get("/api/v1/patients/1/predictions/latest")
        assert response.status_code == 200
        data = response.json()
        assert data is not None
        assert data["id"] == 2
        assert data["patient_id"] == 1
        assert data["risk_probability"] == 0.72
        assert data["risk_level"] == "HIGH"
        assert data["prediction_horizon_days"] == 7
        assert data["model_version"] == "v1.1"
    finally:
        app.dependency_overrides.clear()


def test_latest_prediction_absent_returns_null(client: TestClient, mock_db_session: Session) -> None:
    """Test existing patient without predictions returns HTTP 200 with null payload."""
    app.dependency_overrides[get_db] = lambda: mock_db_session
    try:
        response = client.get("/api/v1/patients/2/predictions/latest")
        assert response.status_code == 200
        assert response.json() is None
    finally:
        app.dependency_overrides.clear()


def test_latest_prediction_patient_not_found(client: TestClient, mock_db_session: Session) -> None:
    """Test missing patient returns HTTP 404."""
    app.dependency_overrides[get_db] = lambda: mock_db_session
    try:
        response = client.get("/api/v1/patients/999/predictions/latest")
        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "HTTP_404"
    finally:
        app.dependency_overrides.clear()


def test_prediction_history(client: TestClient, mock_db_session: Session) -> None:
    """Test prediction history list."""
    app.dependency_overrides[get_db] = lambda: mock_db_session
    try:
        response = client.get("/api/v1/patients/1/predictions")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        assert data["items"][0]["id"] == 2  # Newest first
        assert data["items"][1]["id"] == 1
    finally:
        app.dependency_overrides.clear()
