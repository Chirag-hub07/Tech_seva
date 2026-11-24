"""Health check and service status endpoints."""

from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import APIRouter, status
from pydantic import BaseModel

from backend.app.config import settings
from backend.app.database import verify_database

router = APIRouter(tags=["Health"])


class DatabaseHealth(BaseModel):
    status: str
    connected: bool
    message: str | None = None
    database_time: str | None = None
    tables_count: int | None = None
    tables: list[str] = []
    error: str | None = None


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str
    timestamp: datetime
    database: DatabaseHealth
    cors_allowed_origins: list[str]


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Service Health Check",
    description="Returns backend service health, runtime environment, and safe database connectivity verification.",
)
def get_health() -> HealthResponse:
    """Perform health and database connectivity verification."""
    db_status = verify_database()

    # Determine overall status
    is_db_connected = db_status.get("connected", False)
    overall_status = "healthy" if is_db_connected else "healthy_without_db" if db_status.get("status") == "unconfigured" else "degraded"

    return HealthResponse(
        status=overall_status,
        service=settings.PROJECT_NAME,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        timestamp=datetime.now(timezone.utc),
        database=DatabaseHealth(**db_status),
        cors_allowed_origins=list(settings.CORS_ORIGINS),
    )
