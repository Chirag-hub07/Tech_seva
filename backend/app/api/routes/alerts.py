"""API endpoints for Clinical Alert resources."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.routes.patients import get_patient_or_404
from backend.app.database import get_db
from backend.app.models import Alert
from backend.app.schemas.alert import AlertListResponse, AlertResponse, AlertStatus

router = APIRouter(prefix="/patients", tags=["Alerts"])


@router.get(
    "/{patient_id}/alerts",
    response_model=AlertListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Patient Alerts",
    description=(
        "Retrieve risk notifications for an existing patient. "
        "Supports filtering by lifecycle status (pending, acknowledged, resolved). "
        "Returns an empty collection if no alerts exist."
    ),
)
def get_patient_alerts(
    patient_id: int,
    status_filter: Optional[AlertStatus] = Query(None, alias="status", description="Filter by status: pending, acknowledged, resolved"),
    limit: int = Query(100, ge=1, le=500, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    db: Session = Depends(get_db),
) -> AlertListResponse:
    """Retrieve alerts for an existing patient."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection is not available.",
        )

    # 1. Verify patient exists (raises 404 if missing)
    get_patient_or_404(patient_id, db)

    # 2. Base query
    filters = [Alert.patient_id == patient_id]
    if status_filter:
        filters.append(Alert.status == status_filter.value)

    query = select(Alert).where(*filters).order_by(Alert.created_at.desc(), Alert.id.desc())
    count_query = select(func.count()).select_from(Alert).where(*filters)

    total = db.scalar(count_query) or 0
    records = db.scalars(query.limit(limit).offset(offset)).all()

    return AlertListResponse(
        items=[AlertResponse.model_validate(a) for a in records],
        total=total,
        limit=limit,
        offset=offset,
    )
