"""Live read-only integration tests against the actual Supabase PostgreSQL database.

SAFETY GUARANTEES:
- Strictly read-only queries (SELECT only).
- Zero DDL, zero migrations, zero INSERT, UPDATE, DELETE, or ALTER statements.
- Skips gracefully if DATABASE_URL is unconfigured.
"""

import os
import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.database import verify_database
from backend.app.main import app
from backend.tests.conftest import make_jwt

settings = Settings()
is_db_configured = bool(settings.DATABASE_URL)
run_live_opt_in = os.environ.get("RUN_LIVE_SUPABASE_TESTS") == "1"
should_run_live_tests = is_db_configured and run_live_opt_in


@pytest.mark.skipif(
    not should_run_live_tests,
    reason="Live Supabase tests require DATABASE_URL and RUN_LIVE_SUPABASE_TESTS=1",
)
class TestLiveSupabaseReadOnly:
    """Read-only live database integration test suite."""

    @pytest.fixture(autouse=True)
    def setup_client(self):
        live_token = make_jwt(
            sub="550e8400-e29b-41d4-a716-446655440074",
            email="live.clinician@exacerbalert.org",
            role="clinician",
            patient_ids=[str(i) for i in range(1, 100)] + ["99999"],
        )
        with TestClient(app, headers={"Authorization": f"Bearer {live_token}"}) as client:
            self.client = client

    def test_live_database_connection_status(self):
        """Verify live database connectivity and table count."""
        check = verify_database()
        assert check["connected"] is True
        assert check["tables_count"] == 6
        assert "patients" in check["tables"]
        assert "sensor_measurements" in check["tables"]

    def test_live_get_patients(self):
        """Verify GET /api/v1/patients retrieves the 74 TOLIFE participants."""
        response = self.client.get("/api/v1/patients?limit=10&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 74
        assert len(data["items"]) == 10
        # Check first patient
        first_patient = data["items"][0]
        assert first_patient["id"] == 1
        assert first_patient["participant_id"] == "GER-001"
        assert first_patient["country"] == "GERMANY"

    def test_live_get_patient_by_id(self):
        """Verify GET /api/v1/patients/1 returns patient details."""
        response = self.client.get("/api/v1/patients/1")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["participant_id"] == "GER-001"

    def test_live_get_latest_prediction_empty(self):
        """Verify GET /api/v1/patients/1/predictions/latest returns null (0 predictions in DB)."""
        response = self.client.get("/api/v1/patients/1/predictions/latest")
        assert response.status_code == 200
        assert response.json() is None

    def test_live_get_latest_measurements(self):
        """Verify GET /api/v1/patients/1/measurements/latest returns newest snapshot across sensors."""
        response = self.client.get("/api/v1/patients/1/measurements/latest")
        assert response.status_code == 200
        data = response.json()
        assert data["patient_id"] == 1
        assert data["total_sensors"] > 0
        assert len(data["items"]) == data["total_sensors"]
        # Verify JSONB is preserved
        sample_item = data["items"][0]
        assert "sensor_type" in sample_item
        assert "measurements" in sample_item
        assert isinstance(sample_item["measurements"], dict)
        assert len(sample_item["measurements"]) > 0

    def test_live_get_measurements_series_bri(self):
        """Verify GET /api/v1/patients/1/measurements?sensor_type=BRI&range=7d returns time series."""
        response = self.client.get("/api/v1/patients/1/measurements?sensor_type=BRI&range=7d")
        assert response.status_code == 200
        data = response.json()
        assert data["sensor_type"] == "BRI"
        assert data["range"] == "7d"
        assert data["total"] > 0
        assert len(data["items"]) > 0
        # Check chronological ordering
        timestamps = [item["measured_at"] for item in data["items"]]
        assert timestamps == sorted(timestamps)

    def test_live_get_alerts_empty(self):
        """Verify GET /api/v1/patients/1/alerts returns empty list (0 alerts in DB)."""
        response = self.client.get("/api/v1/patients/1/alerts")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_live_nonexistent_patient_404(self):
        """Verify nonexistent patient returns 404 across all endpoints."""
        assert self.client.get("/api/v1/patients/99999").status_code == 404
        assert self.client.get("/api/v1/patients/99999/predictions/latest").status_code == 404
        assert self.client.get("/api/v1/patients/99999/measurements/latest").status_code == 404
        assert self.client.get("/api/v1/patients/99999/measurements?sensor_type=BRI").status_code == 404
        assert self.client.get("/api/v1/patients/99999/alerts").status_code == 404
