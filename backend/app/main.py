"""FastAPI application entry point for ExacerbAlert Backend Service."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from backend.app.api.routes import admin, alerts, auth, health, measurements, patients, predictions
from backend.app.config import settings
from backend.app.core.exceptions import register_exception_handlers
from backend.app.database import verify_database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backend.app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for safe startup inspection and shutdown."""
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION} [{settings.ENVIRONMENT}]")
    logger.info(f"CORS allowed origins: {settings.CORS_ORIGINS}")

    # Safe database verification check on startup (never runs DDL or modifications)
    db_check = verify_database()
    if db_check.get("connected"):
        logger.info(f"Database connected successfully. Tables verified: {db_check.get('tables')}")
    else:
        logger.warning(f"Database check notice: {db_check.get('message') or db_check.get('error')}")

    yield

    logger.info(f"Shutting down {settings.PROJECT_NAME}")


# Initialize FastAPI instance
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "Production-structured FastAPI backend for the ExacerbAlert COPD Context-Aware Healthcare System. "
        "Provides REST APIs for patient monitoring, sensor telemetry, and model risk predictions."
    ),
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Register CORS Middleware (permitting Vite dev origin http://localhost:5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register centralized exception handlers
register_exception_handlers(app)

# Include routes
# 1. Root /health (standard container & orchestrator health probe)
app.include_router(health.router)
# 2. Versioned /api/v1/health
app.include_router(health.router, prefix=settings.API_V1_PREFIX)

# 3. Read-only REST resources under /api/v1
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(admin.router, prefix=settings.API_V1_PREFIX)
app.include_router(patients.router, prefix=settings.API_V1_PREFIX)
app.include_router(predictions.router, prefix=settings.API_V1_PREFIX)
app.include_router(measurements.router, prefix=settings.API_V1_PREFIX)
app.include_router(alerts.router, prefix=settings.API_V1_PREFIX)


@app.get("/", include_in_schema=False)
def root_redirect() -> RedirectResponse:
    """Redirect root path to interactive Swagger documentation."""
    return RedirectResponse(url="/docs")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.ENVIRONMENT == "development",
    )
