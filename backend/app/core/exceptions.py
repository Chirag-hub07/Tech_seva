"""Centralized error handling and standard error responses for the FastAPI backend."""

import logging
from typing import Any, Dict, Optional
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppException(Exception):
    """Base application exception."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Any] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details


class DatabaseNotConfiguredError(AppException):
    """Raised when an operation requires database connectivity but DATABASE_URL is unset."""

    def __init__(self, message: str = "Database connection is not configured."):
        super().__init__(
            message=message,
            code="DATABASE_UNCONFIGURED",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


def register_exception_handlers(app: FastAPI) -> None:
    """Register centralized error handlers on the FastAPI application."""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        logger.warning(f"Application error [{exc.code}] on {request.method} {request.url.path}: {exc.message}")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        logger.warning(f"HTTPException {exc.status_code} on {request.method} {request.url.path}: {exc.detail}")
        return JSONResponse(
            status_code=exc.status_code,
            headers=getattr(exc, "headers", None),
            content={
                "error": {
                    "code": exc.detail.get("code") if isinstance(exc.detail, dict) and "code" in exc.detail else f"HTTP_{exc.status_code}",
                    "message": exc.detail.get("message") if isinstance(exc.detail, dict) and "message" in exc.detail else (exc.detail if isinstance(exc.detail, str) else "HTTP request error"),
                    "details": exc.detail if not isinstance(exc.detail, str) and not (isinstance(exc.detail, dict) and "message" in exc.detail) else None,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        logger.info(f"Validation error on {request.method} {request.url.path}: {exc.errors()}")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request payload validation failed.",
                    "details": exc.errors(),
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(f"Unhandled error on {request.method} {request.url.path}: {exc}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred while processing the request.",
                    "details": None,
                }
            },
        )
