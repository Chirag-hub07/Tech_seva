"""Pydantic schemas for Clinical Alert resources."""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class AlertStatus(str, Enum):
    """Allowed alert lifecyle statuses."""

    PENDING = "pending"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class AlertLevel(str, Enum):
    """Alert severity tiers."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AlertResponse(BaseModel):
    """Single clinical alert record."""

    id: int = Field(..., description="Unique alert identifier")
    patient_id: int = Field(..., description="Referenced patient identifier")
    prediction_id: Optional[int] = Field(None, description="Linked model prediction, if any")
    alert_level: str = Field(..., description="Alert severity: LOW, MEDIUM, HIGH")
    status: str = Field(..., description="Alert lifecycle status: pending, acknowledged, resolved")
    message: str = Field(..., description="Clinician-facing notification message")
    deduplication_key: Optional[str] = Field(None, description="Idempotency deduplication key")
    acknowledged_at: Optional[datetime] = Field(None, description="Timestamp when alert was acknowledged")
    resolved_at: Optional[datetime] = Field(None, description="Timestamp when alert was resolved")
    created_at: Optional[datetime] = Field(None, description="Timestamp of alert generation")

    model_config = ConfigDict(from_attributes=True)


class AlertListResponse(BaseModel):
    """List of patient alerts with pagination metadata."""

    items: List[AlertResponse] = Field(..., description="Patient alert items")
    total: int = Field(..., description="Total count of alerts matching filter")
    limit: int = Field(..., description="Page limit applied")
    offset: int = Field(..., description="Page offset applied")

    model_config = ConfigDict(from_attributes=True)
