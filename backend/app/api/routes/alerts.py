"""API endpoints for Clinical Alert resources with RBAC enforcement."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.routes.patients import get_patient_or_404
from backend.app.core.auth import get_current_user, require_role, verify_patient_access
from backend.app.database import get_db
from backend.app.models import Alert
from backend.app.schemas.alert import AlertListResponse, AlertResponse, AlertStatus
from backend.app.schemas.auth import AuthenticatedUser, UserRole

router = APIRouter(tags=["Alerts"])


@router.get(
    "/patients/{patient_id}/alerts",
    response_model=AlertListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Patient Alerts",
    description=(
        "Retrieve risk notifications for an existing patient. "
        "Supports filtering by lifecycle status (pending, acknowledged, resolved). "
        "Returns an empty collection if no alerts exist. Requires patient authorization."
    ),
)
def get_patient_alerts(
    patient_id: int,
    status_filter: Optional[AlertStatus] = Query(None, alias="status", description="Filter by status: pending, acknowledged, resolved"),
    limit: int = Query(100, ge=1, le=500, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AlertListResponse:
    """Retrieve alerts for an existing patient with patient access check."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection is not available.",
        )

    # 1. Verify patient-level access with authoritative database session
    verify_patient_access(patient_id, current_user, db=db)

    # 2. Verify patient exists (raises 404 if missing)
    get_patient_or_404(patient_id, db)

    # 3. Base query
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


@router.patch(
    "/alerts/{alert_id}/acknowledge",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    summary="Acknowledge Alert (Gated)",
    description=(
        "Acknowledge a pending clinical alert. Gated write operation: per Phase 3A constraints, "
        "database writes remain strictly disabled until authorization tests pass."
    ),
)
def acknowledge_alert(
    alert_id: int,
    current_user: AuthenticatedUser = Depends(require_role(UserRole.CLINICIAN)),
    db: Session = Depends(get_db),
):
    """Gated alert acknowledgment endpoint with role enforcement."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "code": "WRITES_DISABLED",
            "message": "Alert acknowledgment write operations remain disabled per Phase 3A immutability constraints until authorization tests pass.",
        },
    )
