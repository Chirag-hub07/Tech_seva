"""API endpoints for Patient resources with RBAC and patient-level authorization."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.auth import get_active_patient_assignments, get_current_user, verify_patient_access
from backend.app.database import get_db
from backend.app.models import Patient
from backend.app.schemas.auth import AuthenticatedUser, UserRole
from backend.app.schemas.patient import PatientListResponse, PatientResponse

router = APIRouter(prefix="/patients", tags=["Patients"])


def get_patient_or_404(patient_id: int, db: Session) -> Patient:
    """Retrieve patient by ID or raise 404 HTTPException."""
    patient = db.get(Patient, patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient with ID {patient_id} not found.",
        )
    return patient


@router.get(
    "",
    response_model=PatientListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Patients",
    description="Retrieve paginated list of authorized COPD participants based on caller's role and patient assignments.",
)
def list_patients(
    limit: int = Query(50, ge=1, le=200, description="Maximum patient records to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    country: Optional[str] = Query(None, description="Optional filter by country (e.g. GERMANY, SPAIN)"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PatientListResponse:
    """List patients with pagination metadata and patient-level authorization filtering."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection is not available.",
        )

    # Least privilege: Clinicians and Admins only see assigned patients.
    # Authoritative active patient assignments directly from database (revoked_at IS NULL).
    if current_user.role not in (UserRole.CLINICIAN, UserRole.ADMINISTRATOR):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "FORBIDDEN_UNASSIGNED_ROLE",
                "message": "Access denied. User has no assigned role.",
            },
        )

    allowed_ids = get_active_patient_assignments(current_user.id, db)

    # If clinician or admin without active assigned patients, return empty result
    if not allowed_ids:
        return PatientListResponse(
            items=[],
            total=0,
            limit=limit,
            offset=offset,
        )

    base_query = select(Patient).where(Patient.id.in_(allowed_ids))
    count_query = select(func.count()).select_from(Patient).where(Patient.id.in_(allowed_ids))

    if country:
        normalized_country = country.strip().upper()
        base_query = base_query.where(func.upper(Patient.country) == normalized_country)
        count_query = count_query.where(func.upper(Patient.country) == normalized_country)

    total = db.scalar(count_query) or 0
    items = db.scalars(
        base_query.order_by(Patient.id.asc()).limit(limit).offset(offset)
    ).all()

    return PatientListResponse(
        items=list(items),
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{patient_id}",
    response_model=PatientResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Patient by ID",
    description="Retrieve detailed participant record by unique numeric ID (requires patient authorization).",
)
def get_patient(
    patient_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PatientResponse:
    """Retrieve single patient record with patient-level authorization check."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection is not available.",
        )

    # Verify patient-level access with authoritative database session
    verify_patient_access(patient_id, current_user, db=db)

    patient = get_patient_or_404(patient_id, db)
    return PatientResponse.model_validate(patient)
