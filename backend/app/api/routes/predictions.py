"""API endpoints for Model Prediction resources."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.routes.patients import get_patient_or_404
from backend.app.database import get_db
from backend.app.models import Prediction
from backend.app.schemas.prediction import PredictionHistoryResponse, PredictionResponse

router = APIRouter(prefix="/patients", tags=["Predictions"])


@router.get(
    "/{patient_id}/predictions/latest",
    response_model=Optional[PredictionResponse],
    status_code=status.HTTP_200_OK,
    summary="Get Latest Prediction",
    description=(
        "Retrieve the newest risk prediction for an existing patient. "
        "Returns HTTP 404 if the patient does not exist. "
        "Returns HTTP 200 with JSON null if the patient exists but has no predictions."
    ),
)
def get_latest_prediction(
    patient_id: int,
    db: Session = Depends(get_db),
) -> Optional[PredictionResponse]:
    """Retrieve the newest risk prediction for the patient."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection is not available.",
        )

    # 1. Verify patient exists (raises 404 if missing)
    get_patient_or_404(patient_id, db)

    # 2. Query newest prediction using prediction_timestamp and ID tie-breaker
    stmt = (
        select(Prediction)
        .where(Prediction.patient_id == patient_id)
        .order_by(Prediction.prediction_timestamp.desc(), Prediction.id.desc())
        .limit(1)
    )
    prediction = db.scalar(stmt)

    if not prediction:
        return None

    return PredictionResponse.model_validate(prediction)


@router.get(
    "/{patient_id}/predictions",
    response_model=PredictionHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Prediction History",
    description="Retrieve chronological prediction history for an existing patient.",
)
def get_prediction_history(
    patient_id: int,
    limit: int = Query(50, ge=1, le=200, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    db: Session = Depends(get_db),
) -> PredictionHistoryResponse:
    """Retrieve prediction history for a patient."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection is not available.",
        )

    # Verify patient exists
    get_patient_or_404(patient_id, db)

    base_query = (
        select(Prediction)
        .where(Prediction.patient_id == patient_id)
        .order_by(Prediction.prediction_timestamp.desc(), Prediction.id.desc())
    )
    count_query = select(func.count()).select_from(Prediction).where(Prediction.patient_id == patient_id)

    total = db.scalar(count_query) or 0
    items = db.scalars(base_query.limit(limit).offset(offset)).all()

    return PredictionHistoryResponse(
        items=list(items),
        total=total,
        limit=limit,
        offset=offset,
    )
