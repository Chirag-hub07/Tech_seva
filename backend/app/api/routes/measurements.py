"""API endpoints for Sensor Telemetry resources."""

from datetime import timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.routes.patients import get_patient_or_404
from backend.app.database import get_db
from backend.app.models import SensorMeasurement
from backend.app.schemas.measurement import (
    LatestMeasurementsResponse,
    MeasurementListResponse,
    SensorMeasurementResponse,
    SensorType,
    TimeRange,
)

router = APIRouter(prefix="/patients", tags=["Sensor Telemetry"])


@router.get(
    "/{patient_id}/measurements/latest",
    response_model=LatestMeasurementsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Latest Telemetry by Sensor Type",
    description=(
        "Retrieve the newest measurement record for each available sensor stream "
        "(BRI, EI, MI, PEI, PRVI, SHRI, SII, SQI). Preserves JSONB payloads and validity flags."
    ),
)
def get_latest_measurements(
    patient_id: int,
    db: Session = Depends(get_db),
) -> LatestMeasurementsResponse:
    """Retrieve latest measurement snapshot per sensor type."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection is not available.",
        )

    # 1. Verify patient exists (raises 404 if missing)
    get_patient_or_404(patient_id, db)

    # 2. Query newest record per sensor_type
    dialect_name = db.bind.dialect.name if db.bind else "postgresql"
    if dialect_name == "postgresql":
        # Native PostgreSQL DISTINCT ON for optimal performance
        stmt = (
            select(SensorMeasurement)
            .where(SensorMeasurement.patient_id == patient_id)
            .distinct(SensorMeasurement.sensor_type)
            .order_by(
                SensorMeasurement.sensor_type,
                SensorMeasurement.measured_at.desc(),
                SensorMeasurement.id.desc(),
            )
        )
        items = list(db.scalars(stmt).all())
    else:
        # Generic fallback for SQLite / test environments
        sensors = db.scalars(
            select(SensorMeasurement.sensor_type)
            .where(SensorMeasurement.patient_id == patient_id)
            .distinct()
        ).all()
        items = []
        for s in sensors:
            rec = db.scalar(
                select(SensorMeasurement)
                .where(
                    SensorMeasurement.patient_id == patient_id,
                    SensorMeasurement.sensor_type == s,
                )
                .order_by(SensorMeasurement.measured_at.desc(), SensorMeasurement.id.desc())
                .limit(1)
            )
            if rec:
                items.append(rec)

    # Sort items consistently by sensor_type
    items.sort(key=lambda x: x.sensor_type)

    return LatestMeasurementsResponse(
        items=[SensorMeasurementResponse.model_validate(m) for m in items],
        patient_id=patient_id,
        total_sensors=len(items),
    )


@router.get(
    "/{patient_id}/measurements",
    response_model=MeasurementListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Historical Telemetry Series",
    description=(
        "Retrieve chronological time-series measurements filtered by sensor type and range. "
        "Range windows (7d, 14d, 30d, 60d, 90d, all) are computed relative to the patient's "
        "latest recorded observation to support historical longitudinal records."
    ),
)
def get_measurements_series(
    patient_id: int,
    sensor_type: SensorType = Query(..., description="Sensor type: BRI, EI, MI, PEI, PRVI, SHRI, SII, SQI"),
    range: TimeRange = Query(TimeRange.SEVEN_DAYS, description="Time window: 7d, 14d, 30d, 60d, 90d, all"),
    limit: int = Query(500, ge=1, le=1000, description="Maximum measurement rows to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db),
) -> MeasurementListResponse:
    """Retrieve chronological measurements for a patient and sensor."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection is not available.",
        )

    # 1. Verify patient exists (raises 404 if missing)
    get_patient_or_404(patient_id, db)

    # 2. Determine time window
    base_filter = [
        SensorMeasurement.patient_id == patient_id,
        SensorMeasurement.sensor_type == sensor_type.value,
    ]

    days_lookup = {
        TimeRange.SEVEN_DAYS: 7,
        TimeRange.FOURTEEN_DAYS: 14,
        TimeRange.THIRTY_DAYS: 30,
        TimeRange.SIXTY_DAYS: 60,
        TimeRange.NINETY_DAYS: 90,
    }

    if range != TimeRange.ALL:
        # Find latest measurement date for this patient and sensor stream
        latest_ts = db.scalar(
            select(func.max(SensorMeasurement.measured_at)).where(*base_filter)
        )
        if latest_ts:
            delta_days = days_lookup.get(range, 7)
            cutoff = latest_ts - timedelta(days=delta_days)
            base_filter.append(SensorMeasurement.measured_at >= cutoff)

    # 3. Query records in chronological order
    query = (
        select(SensorMeasurement)
        .where(*base_filter)
        .order_by(SensorMeasurement.measured_at.asc(), SensorMeasurement.id.asc())
    )
    count_query = select(func.count()).select_from(SensorMeasurement).where(*base_filter)

    total = db.scalar(count_query) or 0
    records = db.scalars(query.limit(limit).offset(offset)).all()

    return MeasurementListResponse(
        items=[SensorMeasurementResponse.model_validate(r) for r in records],
        total=total,
        sensor_type=sensor_type.value,
        range=range.value,
        limit=limit,
        offset=offset,
    )
