"""Pydantic schemas for ML Prediction resources."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class PredictionResponse(BaseModel):
    """Prediction output response schema."""

    id: int = Field(..., description="Unique prediction identifier")
    patient_id: int = Field(..., description="Referenced patient identifier")
    prediction_timestamp: datetime = Field(..., description="Timestamp of risk calculation")
    risk_probability: float = Field(..., ge=0.0, le=1.0, description="Predicted exacerbation risk (0.0 to 1.0)")
    risk_level: str = Field(..., description="Categorical risk tier: LOW, MEDIUM, HIGH")
    prediction_horizon_days: int = Field(..., gt=0, description="Forward forecast window in days")
    input_window_start: Optional[datetime] = Field(None, description="Start of historical telemetry window")
    input_window_end: Optional[datetime] = Field(None, description="End of historical telemetry window")
    model_version: Optional[str] = Field(None, description="Identifier of the model generating this score")
    created_at: Optional[datetime] = Field(None, description="Timestamp of record creation")

    model_config = ConfigDict(from_attributes=True)


class PredictionHistoryResponse(BaseModel):
    """Historical predictions for a patient."""

    items: List[PredictionResponse] = Field(..., description="List of predictions")
    total: int = Field(..., description="Total prediction records")
    limit: int = Field(..., description="Applied page limit")
    offset: int = Field(..., description="Applied page offset")

    model_config = ConfigDict(from_attributes=True)
