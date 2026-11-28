"""Application configuration management using Pydantic Settings."""

import json
from pathlib import Path
from typing import List, Optional, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Centralized application settings loaded from environment variables."""

    # Project Information
    PROJECT_NAME: str = "ExacerbAlert Monitoring API"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = Field(default="development", description="Runtime environment: development, staging, production")

    # Server Configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS Allowed Origins
    # Defaults to the active Vite frontend dev origin (http://localhost:5173)
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]

    # Database Configuration (Supabase PostgreSQL via psycopg)
    DATABASE_URL: Optional[str] = Field(
        default=None,
        description="PostgreSQL connection string using psycopg driver (e.g. postgresql+psycopg://...)",
    )
    DB_CONNECT_TIMEOUT: int = Field(default=15, description="Database connection timeout in seconds")
    DB_POOL_PRE_PING: bool = Field(default=True, description="Verify database connections before checkout")
    DB_POOL_RECYCLE: int = Field(default=3600, description="Recycle connections after 1 hour")
    DB_POOL_SIZE: int = Field(default=5, description="SQLAlchemy pool size")
    DB_MAX_OVERFLOW: int = Field(default=10, description="SQLAlchemy pool max overflow")

    # Supabase Authentication & Role-Based Access Control
    SUPABASE_URL: str = Field(
        default="https://odurqfhahaihiplienmz.supabase.co",
        description="Supabase project URL",
    )
    SUPABASE_JWKS_URL: Optional[str] = Field(
        default=None,
        description="Explicit JWKS endpoint URL; defaults to {SUPABASE_URL}/auth/v1/.well-known/jwks.json",
    )
    SUPABASE_JWT_AUDIENCE: str = Field(
        default="authenticated",
        description="Expected JWT audience claim for Supabase Auth",
    )
    SUPABASE_JWT_ISSUER: Optional[str] = Field(
        default=None,
        description="Expected JWT issuer claim; defaults to {SUPABASE_URL}/auth/v1",
    )
    AUTH_ENABLED: bool = Field(
        default=True,
        description="Enforce JWT authentication and RBAC on protected endpoints",
    )
    AUTH_ALGORITHMS: List[str] = Field(
        default=["ES256", "RS256"],
        description="Supported asymmetric JWT signing algorithms",
    )
    JWKS_CACHE_TTL_SECONDS: int = Field(
        default=3600,
        description="JWKS signing key cache TTL in seconds",
    )
    MAX_JWT_LIFETIME_SECONDS: int = Field(
        default=3600,
        description="Maximum allowed token lifespan in seconds (exp - iat)",
    )

    @property
    def effective_jwks_url(self) -> str:
        """Resolve effective JWKS endpoint URL."""
        if self.SUPABASE_JWKS_URL:
            return self.SUPABASE_JWKS_URL
        base = self.SUPABASE_URL.rstrip("/")
        return f"{base}/auth/v1/.well-known/jwks.json"

    @property
    def effective_jwt_issuer(self) -> str:
        """Resolve expected JWT issuer claim."""
        if self.SUPABASE_JWT_ISSUER:
            return self.SUPABASE_JWT_ISSUER
        base = self.SUPABASE_URL.rstrip("/")
        return f"{base}/auth/v1"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, value: Union[str, List[str]]) -> List[str]:
        """Parse CORS origins whether supplied as JSON string, comma-separated string, or list."""
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("[") and value.endswith("]"):
                try:
                    return json.loads(value)
                except Exception:
                    pass
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    model_config = SettingsConfigDict(
        env_file=(
            ROOT_DIR / ".env",
            BACKEND_DIR / ".env",
            ".env",
            "backend/.env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
