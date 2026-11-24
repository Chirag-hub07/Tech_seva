"""Pydantic schemas for Patient resources."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class PatientResponse(BaseModel):
    """Patient record response schema."""

    id: int = Field(..., description="Unique database patient identifier")
    participant_id: str = Field(..., description="Original clinical kit/participant identifier")
    country: Optional[str] = Field(None, description="Country of study participation")
    created_at: Optional[datetime] = Field(None, description="Timestamp of database record creation")

    model_config = ConfigDict(from_attributes=True)


class PatientListResponse(BaseModel):
    """Paginated list of patients with metadata."""

    items: List[PatientResponse] = Field(..., description="List of patient records")
    total: int = Field(..., description="Total count of patient records")
    limit: int = Field(..., description="Page limit applied")
    offset: int = Field(..., description="Page offset applied")

    model_config = ConfigDict(from_attributes=True)
