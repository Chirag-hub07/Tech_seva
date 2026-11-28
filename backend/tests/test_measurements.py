"""Unit and API tests for /patients/{patient_id}/measurements endpoints."""

import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from backend.app.database import Base, get_db
from backend.app.main import app
from backend.app.models import ClinicianPatientAssignment, Patient, SensorMeasurement


@pytest.fixture
def mock_db_session():
    """Create test session with patients and multi-sensor telemetry."""
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

    for pid in (1, 2, 999):
        session.add(
            ClinicianPatientAssignment(
                clinician_id="550e8400-e29b-41d4-a716-446655440001",
                patient_id=pid,
                assigned_by="550e8400-e29b-41d4-a716-446655440002",
            )
        )
    session.commit()

    # Telemetry for Patient 1:
    # BRI: 3 records (10 days ago, 3 days ago, 1 day ago)
    # PEI: 1 invalid record (2 days ago, is_valid=False)
    # EI: 1 record (today)
    m1 = SensorMeasurement(
        id=1,
        patient_id=1,
        sensor_type="BRI",
        measured_at=now - timedelta(days=10),
        measurements={"rf_mean": 17.5, "rf_min": 14.0},
        validity_flags={"flag_quality": 1},
        is_valid=True,
    )
    m2 = SensorMeasurement(
        id=2,
        patient_id=1,
        sensor_type="BRI",
        measured_at=now - timedelta(days=3),
        measurements={"rf_mean": 18.2, "rf_min": 15.1},
        validity_flags={"flag_quality": 1},
        is_valid=True,
    )
    m3 = SensorMeasurement(
        id=3,
        patient_id=1,
        sensor_type="BRI",
        measured_at=now - timedelta(days=1),
        measurements={"rf_mean": 19.0, "rf_min": 16.0},
        validity_flags={"flag_quality": 1},
        is_valid=True,
    )
    m_pei = SensorMeasurement(
        id=4,
        patient_id=1,
        sensor_type="PEI",
        measured_at=now - timedelta(days=2),
        measurements={"mean_PEF": 340.0, "SpO2": 93.0},
        validity_flags={"flag_motion": 0},
        is_valid=False,  # Explicitly invalid
    )
    m_ei = SensorMeasurement(
        id=5,
        patient_id=1,
        sensor_type="EI",
        measured_at=now,
        measurements={"Mean_Temp": 22.4, "Mean_Hum": 45.0},
        validity_flags={"flag_sensor": 1},
        is_valid=True,
    )
    session.add_all([m1, m2, m3, m_pei, m_ei])
    session.commit()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_latest_measurements_per_sensor(client: TestClient, mock_db_session: Session) -> None:
    """Test retrieving latest measurement returns newest record per sensor stream."""
    app.dependency_overrides[get_db] = lambda: mock_db_session
    try:
        response = client.get("/api/v1/patients/1/measurements/latest")
        assert response.status_code == 200
        data = response.json()
        assert data["patient_id"] == 1
        assert data["total_sensors"] == 3
        sensor_types = {item["sensor_type"] for item in data["items"]}
        assert sensor_types == {"BRI", "PEI", "EI"}

        # Verify newest BRI is ID 3 (1 day ago, not ID 1 or 2)
        bri_item = next(item for item in data["items"] if item["sensor_type"] == "BRI")
        assert bri_item["id"] == 3
        assert bri_item["measurements"]["rf_mean"] == 19.0

        # Verify PEI has is_valid = False preserved
        pei_item = next(item for item in data["items"] if item["sensor_type"] == "PEI")
        assert pei_item["is_valid"] is False
        assert pei_item["validity_flags"]["flag_motion"] == 0
    finally:
        app.dependency_overrides.clear()


def test_measurements_series_range_7d(client: TestClient, mock_db_session: Session) -> None:
    """Test 7-day range filter includes records within 7 days of latest measurement."""
    app.dependency_overrides[get_db] = lambda: mock_db_session
    try:
        response = client.get("/api/v1/patients/1/measurements?sensor_type=BRI&range=7d")
        assert response.status_code == 200
        data = response.json()
        assert data["sensor_type"] == "BRI"
        assert data["range"] == "7d"
        # m3 (1d ago) and m2 (3d ago) are within 7 days of m3; m1 (10d ago) is excluded
        assert data["total"] == 2
        assert len(data["items"]) == 2
        assert data["items"][0]["id"] == 2  # Chronological order
        assert data["items"][1]["id"] == 3
    finally:
        app.dependency_overrides.clear()


def test_measurements_series_range_all(client: TestClient, mock_db_session: Session) -> None:
    """Test range=all returns all chronological records."""
    app.dependency_overrides[get_db] = lambda: mock_db_session
    try:
        response = client.get("/api/v1/patients/1/measurements?sensor_type=BRI&range=all")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3
        assert data["items"][0]["id"] == 1
        assert data["items"][1]["id"] == 2
        assert data["items"][2]["id"] == 3
    finally:
        app.dependency_overrides.clear()


def test_empty_measurement_history(client: TestClient, mock_db_session: Session) -> None:
    """Test existing patient with no telemetry for a sensor returns empty list."""
    app.dependency_overrides[get_db] = lambda: mock_db_session
    try:
        response = client.get("/api/v1/patients/2/measurements?sensor_type=BRI&range=7d")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []
    finally:
        app.dependency_overrides.clear()


def test_invalid_sensor_type_returns_422(client: TestClient, mock_db_session: Session) -> None:
    """Test invalid sensor acronym returns 422 Unprocessable Entity."""
    app.dependency_overrides[get_db] = lambda: mock_db_session
    try:
        response = client.get("/api/v1/patients/1/measurements?sensor_type=INVALID_SENSOR")
        assert response.status_code == 422
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "VALIDATION_ERROR"
    finally:
        app.dependency_overrides.clear()


def test_invalid_range_returns_422(client: TestClient, mock_db_session: Session) -> None:
    """Test invalid range parameter returns 422."""
    app.dependency_overrides[get_db] = lambda: mock_db_session
    try:
        response = client.get("/api/v1/patients/1/measurements?sensor_type=BRI&range=365d")
        assert response.status_code == 422
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "VALIDATION_ERROR"
    finally:
        app.dependency_overrides.clear()


def test_measurements_patient_not_found(client: TestClient, mock_db_session: Session) -> None:
    """Test measurement query for nonexistent patient returns 404."""
    app.dependency_overrides[get_db] = lambda: mock_db_session
    try:
        response = client.get("/api/v1/patients/999/measurements?sensor_type=BRI")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
