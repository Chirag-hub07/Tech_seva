"""API endpoints for Patient resources."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import Patient
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
    description="Retrieve paginated list of COPD participants from the verified database.",
)
def list_patients(
    limit: int = Query(50, ge=1, le=200, description="Maximum patient records to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    country: Optional[str] = Query(None, description="Optional filter by country (e.g. GERMANY, SPAIN)"),
    db: Session = Depends(get_db),
) -> PatientListResponse:
    """List patients with pagination metadata."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection is not available.",
        )

    base_query = select(Patient)
    count_query = select(func.count()).select_from(Patient)

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
    description="Retrieve detailed participant record by unique numeric ID.",
)
def get_patient(
    patient_id: int,
    db: Session = Depends(get_db),
) -> PatientResponse:
    """Retrieve single patient record."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection is not available.",
        )
    patient = get_patient_or_404(patient_id, db)
    return PatientResponse.model_validate(patient)
