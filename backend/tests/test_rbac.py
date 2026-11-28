"""Integration tests for Role-Based Access Control (RBAC) and patient-level authorization."""

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.main import app
from backend.tests.conftest import make_jwt


@pytest.fixture(autouse=True)
def setup_mock_db(mock_db_session: Session):
    """Automatically wire in-memory test database for RBAC endpoints."""
    app.dependency_overrides[get_db] = lambda: mock_db_session
    yield
    app.dependency_overrides.pop(get_db, None)


def test_clinician_can_access_auth_me(raw_client: TestClient, clinician_token: str):
    """Verify authenticated clinician receives their profile, role, and permissions."""
    response = raw_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {clinician_token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["role"] == "clinician"
    assert "clinical:read_patients" in data["permissions"]
    assert "clinical:acknowledge_alerts" in data["permissions"]
    assert "admin:manage_users" not in data["permissions"]
    assert data["patient_ids"] == ["1", "2", "3"]


def test_administrator_can_access_auth_me(raw_client: TestClient, admin_token: str):
    """Verify administrator receives their profile, role, and administrative permissions."""
    response = raw_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["role"] == "administrator"
    assert "admin:manage_users" in data["permissions"]
    assert "admin:assign_roles" in data["permissions"]
    # Admin without clinical permissions does not have clinical permissions
    assert "clinical:read_patients" not in data["permissions"]


def test_clinician_access_to_authorized_patient(raw_client: TestClient, clinician_token: str):
    """Verify clinician can access an authorized patient profile (patient 1)."""
    response = raw_client.get(
        "/api/v1/patients/1",
        headers={"Authorization": f"Bearer {clinician_token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == 1
    assert data["participant_id"] == "TEST-001"


def test_clinician_denial_for_unauthorized_patient(raw_client: TestClient, clinician_token: str):
    """Verify clinician is denied access (HTTP 403) for patient 99 (not in their patient_ids)."""
    response = raw_client.get(
        "/api/v1/patients/99",
        headers={"Authorization": f"Bearer {clinician_token}"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    data = response.json()
    assert "FORBIDDEN" in data["error"]["code"]
    assert "not authorized to access records for patient 99" in data["error"]["message"]


def test_clinician_denial_for_unauthorized_patient_measurements(raw_client: TestClient, clinician_token: str):
    """Verify clinician is denied telemetry access (HTTP 403) for unauthorized patient 99."""
    latest_resp = raw_client.get(
        "/api/v1/patients/99/measurements/latest",
        headers={"Authorization": f"Bearer {clinician_token}"},
    )
    assert latest_resp.status_code == status.HTTP_403_FORBIDDEN

    range_resp = raw_client.get(
        "/api/v1/patients/99/measurements?sensor_type=BRI&range=7d",
        headers={"Authorization": f"Bearer {clinician_token}"},
    )
    assert range_resp.status_code == status.HTTP_403_FORBIDDEN


def test_clinician_denial_for_unauthorized_patient_predictions(raw_client: TestClient, clinician_token: str):
    """Verify clinician is denied prediction access (HTTP 403) for unauthorized patient 99."""
    latest_resp = raw_client.get(
        "/api/v1/patients/99/predictions/latest",
        headers={"Authorization": f"Bearer {clinician_token}"},
    )
    assert latest_resp.status_code == status.HTTP_403_FORBIDDEN

    hist_resp = raw_client.get(
        "/api/v1/patients/99/predictions",
        headers={"Authorization": f"Bearer {clinician_token}"},
    )
    assert hist_resp.status_code == status.HTTP_403_FORBIDDEN


def test_clinician_denial_for_unauthorized_patient_alerts(raw_client: TestClient, clinician_token: str):
    """Verify clinician is denied alert access (HTTP 403) for unauthorized patient 99."""
    response = raw_client.get(
        "/api/v1/patients/99/alerts",
        headers={"Authorization": f"Bearer {clinician_token}"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_clinician_patient_list_only_contains_authorized_patients(raw_client: TestClient, clinician_token: str):
    """Verify clinician patient list query filters strictly by authorized patient IDs."""
    response = raw_client.get(
        "/api/v1/patients",
        headers={"Authorization": f"Bearer {clinician_token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    # Clinician token has patient_ids: ['1', '2', '3']
    patient_ids_returned = [p["id"] for p in data["items"]]
    assert all(pid in [1, 2, 3] for pid in patient_ids_returned)


def test_clinician_with_no_patient_assignments_sees_empty_list(raw_client: TestClient):
    """Verify clinician with zero patient assignments sees empty collection (deny by default)."""
    unassigned_clinician_token = make_jwt(
        sub="550e8400-e29b-41d4-a716-446655440009",
        role="clinician",
        patient_ids=[],
    )
    response = raw_client.get(
        "/api/v1/patients",
        headers={"Authorization": f"Bearer {unassigned_clinician_token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_administrator_denied_clinical_records_without_clinical_permission(
    raw_client: TestClient,
    admin_token: str,
):
    """LEAST PRIVILEGE TEST: Administrator cannot view clinical records without explicit clinical permission."""
    response = raw_client.get(
        "/api/v1/patients/1",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "Administrator role does not grant clinical data access" in response.json()["error"]["message"]


def test_administrator_with_explicit_patient_assignment_can_access_patient(
    raw_client: TestClient,
    admin_with_patients_token: str,
):
    """Verify administrator granted explicit clinical patient permission can view that patient."""
    response = raw_client.get(
        "/api/v1/patients/1",
        headers={"Authorization": f"Bearer {admin_with_patients_token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == 1


def test_administrator_can_access_user_management(raw_client: TestClient, admin_token: str):
    """Verify administrator can access the user management endpoint."""
    response = raw_client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response.json(), list)


def test_clinician_denied_user_management(raw_client: TestClient, clinician_token: str):
    """Verify clinician is denied access (HTTP 403) to administrator user management."""
    response = raw_client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {clinician_token}"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    data = response.json()
    assert "FORBIDDEN" in data["error"]["code"]


def test_prevention_of_self_promotion_to_administrator(raw_client: TestClient, clinician_token: str):
    """Verify non-admin cannot call role assignment endpoint to escalate privileges."""
    response = raw_client.post(
        "/api/v1/admin/users/550e8400-e29b-41d4-a716-446655440001/role",
        headers={"Authorization": f"Bearer {clinician_token}"},
        json={"role": "administrator"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_unassigned_user_denied_all_clinical_and_admin_resources(raw_client: TestClient):
    """Verify user with valid token but no role claim is denied clinical and admin resources."""
    no_role_token = make_jwt(role=None)

    # Denied admin
    admin_resp = raw_client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {no_role_token}"},
    )
    assert admin_resp.status_code == status.HTTP_403_FORBIDDEN

    # Denied patient details
    patient_resp = raw_client.get(
        "/api/v1/patients/1",
        headers={"Authorization": f"Bearer {no_role_token}"},
    )
    assert patient_resp.status_code == status.HTTP_403_FORBIDDEN


def test_alert_acknowledgment_writes_remain_disabled(raw_client: TestClient, clinician_token: str):
    """Verify alert acknowledgment returns HTTP 501 Not Implemented (writes safely disabled)."""
    response = raw_client.patch(
        "/api/v1/alerts/1/acknowledge",
        headers={"Authorization": f"Bearer {clinician_token}"},
    )
    assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
    data = response.json()
    assert "WRITES_DISABLED" in data["error"]["code"]


def test_admin_self_demotion_prevention(raw_client: TestClient, admin_token: str):
    """SECURITY TEST: Administrators cannot demote themselves to prevent lockout."""
    # admin_token subject is "550e8400-e29b-41d4-a716-446655440002"
    response = raw_client.post(
        "/api/v1/admin/users/550e8400-e29b-41d4-a716-446655440002/role",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"role": "clinician"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    msg = data.get("error", {}).get("message") or data.get("detail", "")
    assert "Self-demotion protection" in msg


def test_non_admin_cannot_assign_patient_access(raw_client: TestClient, clinician_token: str):
    """SECURITY TEST: Clinicians cannot assign patient access to users."""
    response = raw_client.post(
        "/api/v1/admin/users/550e8400-e29b-41d4-a716-446655440001/patient-access",
        headers={"Authorization": f"Bearer {clinician_token}"},
        json={"patient_ids": ["1", "2", "3", "99"]},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_revoked_patient_assignment_denied(raw_client: TestClient, mock_db_session: Session):
    """SECURITY TEST: When a patient assignment is revoked in database, access is denied immediately."""
    from datetime import datetime, timezone
    from backend.app.models import ClinicianPatientAssignment
    cpa = ClinicianPatientAssignment(
        clinician_id="550e8400-e29b-41d4-a716-446655440010",
        patient_id=1,
        assigned_by="550e8400-e29b-41d4-a716-446655440002",
    )
    mock_db_session.add(cpa)
    mock_db_session.commit()

    # Active assignment: clinician has patient 1
    active_token = make_jwt(
        sub="550e8400-e29b-41d4-a716-446655440010",
        role="clinician",
        patient_ids=["1"],
    )
    resp_ok = raw_client.get(
        "/api/v1/patients/1",
        headers={"Authorization": f"Bearer {active_token}"},
    )
    assert resp_ok.status_code == status.HTTP_200_OK

    # Revoke assignment in database
    cpa.revoked_at = datetime.now(timezone.utc)
    cpa.revoked_by = "550e8400-e29b-41d4-a716-446655440002"
    mock_db_session.commit()

    # Immediate rejection even with the same unexpired active_token
    resp_denied = raw_client.get(
        "/api/v1/patients/1",
        headers={"Authorization": f"Bearer {active_token}"},
    )
    assert resp_denied.status_code == status.HTTP_403_FORBIDDEN
    assert "not authorized to access records for patient 1" in resp_denied.json()["error"]["message"]


def test_authoritative_demotion_rejects_existing_admin_jwt(raw_client: TestClient, admin_token: str, mock_db_session: Session):
    """SECURITY TEST: An administrator demoted in auth.users is immediately rejected on sensitive routes."""
    from sqlalchemy import text
    # Seed target user to modify
    mock_db_session.execute(text("""
        INSERT OR REPLACE INTO auth.users (id, email, raw_app_meta_data)
        VALUES ('550e8400-e29b-41d4-a716-446655440099', 'target@test.org', '{"role": "clinician"}');
    """))
    # Authoritative demotion: change admin role in auth.users to clinician
    mock_db_session.execute(text("""
        UPDATE auth.users 
        SET raw_app_meta_data = '{"role": "clinician"}' 
        WHERE id = '550e8400-e29b-41d4-a716-446655440002';
    """))
    mock_db_session.commit()

    # Attempt sensitive admin action presenting old valid administrator JWT
    response = raw_client.post(
        "/api/v1/admin/users/550e8400-e29b-41d4-a716-446655440099/role",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"role": "administrator"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    data = response.json()
    err_code = data.get("error", {}).get("code") or data.get("detail", {}).get("code")
    assert err_code == "ROLE_DEMOTED"


def test_banned_account_with_existing_token_rejected(raw_client: TestClient, admin_token: str, mock_db_session: Session):
    """SECURITY TEST: A banned user presenting an unexpired JWT is immediately rejected on sensitive routes."""
    from sqlalchemy import text
    from datetime import datetime, timezone, timedelta
    future_ban = datetime.now(timezone.utc) + timedelta(days=7)
    mock_db_session.execute(text("""
        UPDATE auth.users 
        SET raw_app_meta_data = '{"role": "administrator"}',
            banned_until = :ban 
        WHERE id = '550e8400-e29b-41d4-a716-446655440002';
    """), {"ban": future_ban})
    mock_db_session.commit()

    response = raw_client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    data = response.json()
    err_code = data.get("error", {}).get("code") or data.get("detail", {}).get("code")
    assert err_code == "ACCOUNT_BANNED"


def test_deleted_account_with_existing_token_rejected(raw_client: TestClient, admin_token: str, mock_db_session: Session):
    """SECURITY TEST: A soft-deleted user presenting an unexpired JWT is immediately rejected on sensitive routes."""
    from sqlalchemy import text
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    mock_db_session.execute(text("""
        UPDATE auth.users 
        SET raw_app_meta_data = '{"role": "administrator"}',
            banned_until = NULL,
            deleted_at = :del_time 
        WHERE id = '550e8400-e29b-41d4-a716-446655440002';
    """), {"del_time": now})
    mock_db_session.commit()

    response = raw_client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    data = response.json()
    err_code = data.get("error", {}).get("code") or data.get("detail", {}).get("code")
    assert err_code == "ACCOUNT_DELETED"


def test_valid_unchanged_account_succeeds(raw_client: TestClient, admin_token: str, mock_db_session: Session):
    """SECURITY TEST: Active, unbanned administrator with matching role succeeds on sensitive routes."""
    from sqlalchemy import text
    mock_db_session.execute(text("""
        UPDATE auth.users 
        SET raw_app_meta_data = '{"role": "administrator"}',
            banned_until = NULL,
            deleted_at = NULL 
        WHERE id = '550e8400-e29b-41d4-a716-446655440002';
    """))
    mock_db_session.commit()

    response = raw_client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response.json(), list)


def test_authoritative_revocation_across_all_six_clinical_read_endpoints(
    raw_client: TestClient,
    mock_db_session: Session,
):
    """PHASE 3B.1.18 CORE VERIFICATION:

    1. Active database assignment exists: Clinician accesses all 6 clinical read endpoints (200 OK).
    2. Database assignment is revoked (revoked_at is set).
    3. Presenting the same valid, unexpired JWT results in HTTP 403 FORBIDDEN_PATIENT_ACCESS
       across all clinical read endpoints, and patient disappears from GET /api/v1/patients.
    """
    from datetime import datetime, timezone, timedelta
    from backend.app.models import Alert, ClinicianPatientAssignment, Prediction, SensorMeasurement

    clinician_id = "550e8400-e29b-41d4-a716-446655440020"
    admin_id = "550e8400-e29b-41d4-a716-446655440002"
    now = datetime.now(timezone.utc)

    # Seed telemetry, prediction, and alert for patient 1 to guarantee 200 OK on all paths
    mock_db_session.add(
        SensorMeasurement(
            id=101,
            patient_id=1,
            sensor_type="BRI",
            measured_at=now,
            measurements={"rf_mean": 18.0},
            validity_flags={},
            is_valid=True,
        )
    )
    mock_db_session.add(
        Prediction(
            id=101,
            patient_id=1,
            prediction_timestamp=now,
            risk_probability=0.42,
            risk_level="MEDIUM",
            prediction_horizon_days=7,
            model_version="v1.0",
            created_at=now,
        )
    )
    mock_db_session.add(
        Alert(
            id=101,
            patient_id=1,
            alert_level="MEDIUM",
            status="pending",
            message="Test verification alert",
            deduplication_key="test-dedup-3b-18",
            created_at=now,
        )
    )
    # Seed active assignment in database
    assignment = ClinicianPatientAssignment(
        clinician_id=clinician_id,
        patient_id=1,
        assigned_by=admin_id,
    )
    mock_db_session.add(assignment)
    mock_db_session.commit()

    # Generate clinician JWT containing patient 1 in token claims
    token = make_jwt(
        sub=clinician_id,
        email="clinician.revocation.test@exacerbalert.org",
        role="clinician",
        patient_ids=["1"],
        expires_in_seconds=3600,
    )
    auth_header = {"Authorization": f"Bearer {token}"}

    # Step 1: Active assignment state -> All 6 clinical read endpoints succeed (200 OK)
    resp_patient = raw_client.get("/api/v1/patients/1", headers=auth_header)
    assert resp_patient.status_code == status.HTTP_200_OK
    assert resp_patient.json()["id"] == 1

    resp_list = raw_client.get("/api/v1/patients", headers=auth_header)
    assert resp_list.status_code == status.HTTP_200_OK
    pids = [p["id"] for p in resp_list.json()["items"]]
    assert 1 in pids

    resp_latest_m = raw_client.get("/api/v1/patients/1/measurements/latest", headers=auth_header)
    assert resp_latest_m.status_code == status.HTTP_200_OK

    resp_series_m = raw_client.get("/api/v1/patients/1/measurements?sensor_type=BRI", headers=auth_header)
    assert resp_series_m.status_code == status.HTTP_200_OK

    resp_latest_p = raw_client.get("/api/v1/patients/1/predictions/latest", headers=auth_header)
    assert resp_latest_p.status_code == status.HTTP_200_OK

    resp_hist_p = raw_client.get("/api/v1/patients/1/predictions", headers=auth_header)
    assert resp_hist_p.status_code == status.HTTP_200_OK

    resp_alerts = raw_client.get("/api/v1/patients/1/alerts", headers=auth_header)
    assert resp_alerts.status_code == status.HTTP_200_OK

    # Step 2: Revoke assignment in database
    assignment.revoked_at = datetime.now(timezone.utc)
    assignment.revoked_by = admin_id
    mock_db_session.commit()

    # Step 3: Present SAME unexpired JWT -> All endpoints immediately reject or exclude
    # 3a. GET /api/v1/patients/1 -> 403 Forbidden
    r1 = raw_client.get("/api/v1/patients/1", headers=auth_header)
    assert r1.status_code == status.HTTP_403_FORBIDDEN
    assert r1.json()["error"]["code"] == "FORBIDDEN_PATIENT_ACCESS"

    # 3b. GET /api/v1/patients -> 200 OK with empty items list (patient 1 excluded)
    r_list = raw_client.get("/api/v1/patients", headers=auth_header)
    assert r_list.status_code == status.HTTP_200_OK
    assert r_list.json()["items"] == []
    assert r_list.json()["total"] == 0

    # 3c. GET /api/v1/patients/1/measurements/latest -> 403 Forbidden
    r_ml = raw_client.get("/api/v1/patients/1/measurements/latest", headers=auth_header)
    assert r_ml.status_code == status.HTTP_403_FORBIDDEN
    assert r_ml.json()["error"]["code"] == "FORBIDDEN_PATIENT_ACCESS"

    # 3d. GET /api/v1/patients/1/measurements?sensor_type=BRI -> 403 Forbidden
    r_ms = raw_client.get("/api/v1/patients/1/measurements?sensor_type=BRI", headers=auth_header)
    assert r_ms.status_code == status.HTTP_403_FORBIDDEN
    assert r_ms.json()["error"]["code"] == "FORBIDDEN_PATIENT_ACCESS"

    # 3e. GET /api/v1/patients/1/predictions/latest -> 403 Forbidden
    r_pl = raw_client.get("/api/v1/patients/1/predictions/latest", headers=auth_header)
    assert r_pl.status_code == status.HTTP_403_FORBIDDEN
    assert r_pl.json()["error"]["code"] == "FORBIDDEN_PATIENT_ACCESS"

    # 3f. GET /api/v1/patients/1/predictions -> 403 Forbidden
    r_ph = raw_client.get("/api/v1/patients/1/predictions", headers=auth_header)
    assert r_ph.status_code == status.HTTP_403_FORBIDDEN
    assert r_ph.json()["error"]["code"] == "FORBIDDEN_PATIENT_ACCESS"

    # 3g. GET /api/v1/patients/1/alerts -> 403 Forbidden
    r_al = raw_client.get("/api/v1/patients/1/alerts", headers=auth_header)
    assert r_al.status_code == status.HTTP_403_FORBIDDEN
    assert r_al.json()["error"]["code"] == "FORBIDDEN_PATIENT_ACCESS"


def test_cross_clinician_assignment_isolation(raw_client: TestClient, mock_db_session: Session):
    """SECURITY TEST: Clinician B cannot access Clinician A's patient, even if claimed in token."""
    from backend.app.models import ClinicianPatientAssignment

    clinician_a_id = "550e8400-e29b-41d4-a716-446655440021"
    clinician_b_id = "550e8400-e29b-41d4-a716-446655440022"
    admin_id = "550e8400-e29b-41d4-a716-446655440002"

    # Assign patient 1 strictly to Clinician A
    mock_db_session.add(
        ClinicianPatientAssignment(
            clinician_id=clinician_a_id,
            patient_id=1,
            assigned_by=admin_id,
        )
    )
    # Assign patient 2 strictly to Clinician B
    mock_db_session.add(
        ClinicianPatientAssignment(
            clinician_id=clinician_b_id,
            patient_id=2,
            assigned_by=admin_id,
        )
    )
    mock_db_session.commit()

    # Clinician B presents token claiming patient 1 and 2
    token_b = make_jwt(
        sub=clinician_b_id,
        email="clinician.b@exacerbalert.org",
        role="clinician",
        patient_ids=["1", "2"],
    )
    auth_b = {"Authorization": f"Bearer {token_b}"}

    # Clinician B can access patient 2
    resp_p2 = raw_client.get("/api/v1/patients/2", headers=auth_b)
    assert resp_p2.status_code == status.HTTP_200_OK

    # Clinician B is DENIED access to patient 1 (HTTP 403) despite token claim
    resp_p1 = raw_client.get("/api/v1/patients/1", headers=auth_b)
    assert resp_p1.status_code == status.HTTP_403_FORBIDDEN
    assert resp_p1.json()["error"]["code"] == "FORBIDDEN_PATIENT_ACCESS"

    # In patient list, Clinician B only sees patient 2
    resp_list = raw_client.get("/api/v1/patients", headers=auth_b)
    assert resp_list.status_code == status.HTTP_200_OK
    returned_ids = [p["id"] for p in resp_list.json()["items"]]
    assert returned_ids == [2]


def test_administrator_without_assignment_denied_all_clinical_reads(
    raw_client: TestClient,
    admin_token: str,
):
    """LEAST PRIVILEGE TEST: Administrator without active assignment is denied all clinical read endpoints."""
    auth_header = {"Authorization": f"Bearer {admin_token}"}

    # Patient record
    resp_patient = raw_client.get("/api/v1/patients/1", headers=auth_header)
    assert resp_patient.status_code == status.HTTP_403_FORBIDDEN
    assert resp_patient.json()["error"]["code"] == "FORBIDDEN_CLINICAL_ACCESS"

    # Telemetry
    resp_m = raw_client.get("/api/v1/patients/1/measurements/latest", headers=auth_header)
    assert resp_m.status_code == status.HTTP_403_FORBIDDEN
    assert resp_m.json()["error"]["code"] == "FORBIDDEN_CLINICAL_ACCESS"

    # Predictions
    resp_p = raw_client.get("/api/v1/patients/1/predictions/latest", headers=auth_header)
    assert resp_p.status_code == status.HTTP_403_FORBIDDEN
    assert resp_p.json()["error"]["code"] == "FORBIDDEN_CLINICAL_ACCESS"

    # Alerts
    resp_a = raw_client.get("/api/v1/patients/1/alerts", headers=auth_header)
    assert resp_a.status_code == status.HTTP_403_FORBIDDEN
    assert resp_a.json()["error"]["code"] == "FORBIDDEN_CLINICAL_ACCESS"

    # Patient list returns empty collection (0 items)
    resp_list = raw_client.get("/api/v1/patients", headers=auth_header)
    assert resp_list.status_code == status.HTTP_200_OK
    assert resp_list.json()["items"] == []
    assert resp_list.json()["total"] == 0


def test_dynamic_assignment_accessible_immediately_without_token_refresh(
    raw_client: TestClient,
    mock_db_session: Session,
):
    """AUTHORITATIVE ASSIGNMENT TEST: Newly added DB assignment is accessible immediately without re-issuing JWT."""
    from backend.app.models import ClinicianPatientAssignment

    clinician_id = "550e8400-e29b-41d4-a716-446655440023"
    admin_id = "550e8400-e29b-41d4-a716-446655440002"

    # Issue token with empty patient_ids claim
    token = make_jwt(
        sub=clinician_id,
        email="clinician.dynamic@exacerbalert.org",
        role="clinician",
        patient_ids=[],
    )
    auth_header = {"Authorization": f"Bearer {token}"}

    # Before DB assignment: denied
    resp_before = raw_client.get("/api/v1/patients/2", headers=auth_header)
    assert resp_before.status_code == status.HTTP_403_FORBIDDEN

    # Add active database assignment
    mock_db_session.add(
        ClinicianPatientAssignment(
            clinician_id=clinician_id,
            patient_id=2,
            assigned_by=admin_id,
        )
    )
    mock_db_session.commit()

    # Immediately accessible with the SAME token
    resp_after = raw_client.get("/api/v1/patients/2", headers=auth_header)
    assert resp_after.status_code == status.HTTP_200_OK
    assert resp_after.json()["id"] == 2

    # Patient appears in GET /api/v1/patients immediately
    resp_list = raw_client.get("/api/v1/patients", headers=auth_header)
    assert resp_list.status_code == status.HTTP_200_OK
    pids = [p["id"] for p in resp_list.json()["items"]]
    assert 2 in pids


def test_sequential_revocation_transaction_ordering(
    raw_client: TestClient,
    mock_db_session: Session,
):
    """SEQUENTIAL TRANSACTION ORDERING TEST:

    Verifies sequential state transitions before and after an assignment revocation commit:
    1. Pre-revocation request: Starts and completes while assignment is active -> succeeds (HTTP 200 OK).
    2. Revocation commit: Transaction commits setting revoked_at timestamp.
    3. Post-revocation request: Any request whose assignment check executes after the revocation commits
       is strictly guaranteed to be denied (HTTP 403 FORBIDDEN_PATIENT_ACCESS).

    Note on in-flight requests:
    Under standard READ COMMITTED isolation, an in-flight read request that already passed its assignment check
    before the revocation transaction commits will complete its clinical data read; revocation does not
    retroactively abort or cancel in-flight HTTP connections.
    """
    from datetime import datetime, timezone
    from backend.app.models import ClinicianPatientAssignment

    clinician_id = "550e8400-e29b-41d4-a716-446655440050"
    admin_id = "550e8400-e29b-41d4-a716-446655440002"

    # Seed active assignment
    assignment = ClinicianPatientAssignment(
        clinician_id=clinician_id,
        patient_id=1,
        assigned_by=admin_id,
    )
    mock_db_session.add(assignment)
    mock_db_session.commit()

    token = make_jwt(
        sub=clinician_id,
        email="clinician.concurrency@exacerbalert.org",
        role="clinician",
        patient_ids=["1"],
    )
    auth_header = {"Authorization": f"Bearer {token}"}

    # Pre-revocation request succeeds
    r_pre = raw_client.get("/api/v1/patients/1", headers=auth_header)
    assert r_pre.status_code == status.HTTP_200_OK

    # Simulate Revocation transaction commit
    assignment.revoked_at = datetime.now(timezone.utc)
    assignment.revoked_by = admin_id
    mock_db_session.commit()

    # Guaranteed post-revocation denial
    r_post = raw_client.get("/api/v1/patients/1", headers=auth_header)
    assert r_post.status_code == status.HTTP_403_FORBIDDEN
    assert r_post.json()["error"]["code"] == "FORBIDDEN_PATIENT_ACCESS"


def test_unassigned_nonexistent_patient_denies_with_403_preventing_enumeration(
    raw_client: TestClient,
    mock_db_session: Session,
):
    """ANTI-ENUMERATION SECURITY TEST:

    1. Unassigned caller querying non-existent patient 888888 receives HTTP 403 Forbidden,
       preventing information disclosure (patient existence enumeration oracle).
    2. Assigned caller querying non-existent patient 888888 passes assignment check and
       receives HTTP 404 Not Found.
    """
    from backend.app.models import ClinicianPatientAssignment

    clinician_id = "550e8400-e29b-41d4-a716-446655440060"
    admin_id = "550e8400-e29b-41d4-a716-446655440002"
    non_existent_pid = 888888

    # Token for clinician without assignment to 888888
    token = make_jwt(
        sub=clinician_id,
        email="clinician.enumeration@exacerbalert.org",
        role="clinician",
        patient_ids=[],
    )
    auth_header = {"Authorization": f"Bearer {token}"}

    # Step 1: Without assignment, unassigned non-existent patient returns 403 Forbidden
    r_unassigned = raw_client.get(f"/api/v1/patients/{non_existent_pid}", headers=auth_header)
    assert r_unassigned.status_code == status.HTTP_403_FORBIDDEN
    assert r_unassigned.json()["error"]["code"] == "FORBIDDEN_PATIENT_ACCESS"

    # Step 2: Grant assignment to 888888 in DB (e.g. valid referral for patient not yet onboarded)
    mock_db_session.add(
        ClinicianPatientAssignment(
            clinician_id=clinician_id,
            patient_id=non_existent_pid,
            assigned_by=admin_id,
        )
    )
    mock_db_session.commit()

    # Step 3: Now authorized to know existence; receives 404 Not Found because patient is not in patients table
    r_assigned = raw_client.get(f"/api/v1/patients/{non_existent_pid}", headers=auth_header)
    assert r_assigned.status_code == status.HTTP_404_NOT_FOUND
    assert f"Patient with ID {non_existent_pid} not found" in r_assigned.json()["error"]["message"]

