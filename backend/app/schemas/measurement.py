"""Pydantic schemas for Sensor Telemetry resources."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class SensorType(str, Enum):
    """Permitted 8 TOLIFE sensor streams."""

    BRI = "BRI"      # Breathing Rate Index
    EI = "EI"        # Environmental Index
    MI = "MI"        # Mobility Index
    PEI = "PEI"      # Pulmonary Efficiency Index
    PRVI = "PRVI"    # Pulse Rate Variability Index
    SHRI = "SHRI"    # Sleeping Heart Rate Index
    SII = "SII"      # Sound Intensity Index
    SQI = "SQI"      # Sleep Quality Index


class TimeRange(str, Enum):
    """Supported historical time windows."""

    SEVEN_DAYS = "7d"
    FOURTEEN_DAYS = "14d"
    THIRTY_DAYS = "30d"
    SIXTY_DAYS = "60d"
    NINETY_DAYS = "90d"
    ALL = "all"


class SensorMeasurementResponse(BaseModel):
    """Single sensor telemetry record preserving JSONB structures."""

    id: int = Field(..., description="Unique record identifier")
    patient_id: int = Field(..., description="Referenced patient identifier")
    sensor_type: str = Field(..., description="Sensor stream acronym (e.g. BRI, PEI)")
    measured_at: datetime = Field(..., description="UTC timestamp of the telemetry observation")
    measurements: Dict[str, Any] = Field(..., description="Original metric key-value pairs preserved as JSONB")
    validity_flags: Optional[Dict[str, Any]] = Field(None, description="Original validity flags preserved as JSONB")
    is_valid: Optional[bool] = Field(None, description="Cleaned boolean validity indicator")
    created_at: Optional[datetime] = Field(None, description="Database record timestamp")

    model_config = ConfigDict(from_attributes=True)


class LatestMeasurementsResponse(BaseModel):
    """Snapshot of the latest record for each sensor type."""

    items: List[SensorMeasurementResponse] = Field(..., description="Latest measurement per sensor stream")
    patient_id: int = Field(..., description="Patient identifier")
    total_sensors: int = Field(..., description="Number of sensor streams with data")

    model_config = ConfigDict(from_attributes=True)


class MeasurementListResponse(BaseModel):
    """Chronological historical telemetry series."""

    items: List[SensorMeasurementResponse] = Field(..., description="Chronological telemetry records")
    total: int = Field(..., description="Total matching records")
    sensor_type: str = Field(..., description="Filtered sensor stream")
    range: str = Field(..., description="Applied time window")
    limit: int = Field(..., description="Applied page limit")
    offset: int = Field(..., description="Applied page offset")

    model_config = ConfigDict(from_attributes=True)
