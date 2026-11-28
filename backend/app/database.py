"""SQLAlchemy database engine, session handling, and safe connectivity inspection."""

import logging
from typing import Any, Dict, Generator, Optional
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from backend.app.config import settings

logger = logging.getLogger(__name__)

# Base class for SQLAlchemy declarative models
Base = declarative_base()

_engine: Optional[Engine] = None
_SessionFactory: Optional[sessionmaker] = None


def get_engine() -> Optional[Engine]:
    """Retrieve or lazily initialize the SQLAlchemy engine."""
    global _engine, _SessionFactory

    # Check settings, and reload from environment if not yet populated
    db_url = settings.DATABASE_URL
    if not db_url:
        from backend.app.config import Settings
        db_url = Settings().DATABASE_URL

    if not db_url:
        logger.warning("DATABASE_URL is not configured. Database operations will be disabled.")
        return None

    if _engine is not None:
        return _engine

    # Normalize PostgreSQL URL to use the psycopg driver if needed
    normalized_url = db_url
    if normalized_url.startswith("postgresql://"):
        normalized_url = normalized_url.replace("postgresql://", "postgresql+psycopg://", 1)
    elif normalized_url.startswith("postgres://"):
        normalized_url = normalized_url.replace("postgres://", "postgresql+psycopg://", 1)

    connect_args: Dict[str, Any] = {
        "connect_timeout": settings.DB_CONNECT_TIMEOUT,
        "prepare_threshold": None,  # Required for PgBouncer transaction pooling in psycopg3
    }

    try:
        _engine = create_engine(
            normalized_url,
            connect_args=connect_args,
            pool_pre_ping=settings.DB_POOL_PRE_PING,
            pool_recycle=settings.DB_POOL_RECYCLE,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
        )
        _SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
        logger.info("SQLAlchemy engine initialized with psycopg driver.")
        return _engine
    except Exception as exc:
        logger.error(f"Failed to initialize database engine: {exc}")
        return None


def get_session_factory() -> Optional[sessionmaker]:
    """Retrieve the sessionmaker factory."""
    global _SessionFactory
    if _SessionFactory is None:
        get_engine()
    return _SessionFactory


def get_db() -> Generator[Optional[Session], None, None]:
    """FastAPI dependency for yielding database sessions."""
    factory = get_session_factory()
    if factory is None:
        yield None
        return

    session: Session = factory()
    try:
        yield session
    finally:
        session.close()


def verify_database() -> Dict[str, Any]:
    """Safely verify connectivity and inspect existing metadata without altering any tables.

    CRITICAL SAFETY RULES:
    - Never calls Base.metadata.create_all()
    - Never executes DDL or migrations
    - Never alters, truncates, or seeds tables
    - Read-only metadata inspection and ping
    """
    db_url = settings.DATABASE_URL
    if not db_url:
        from backend.app.config import Settings
        db_url = Settings().DATABASE_URL

    if not db_url:
        return {
            "status": "unconfigured",
            "connected": False,
            "message": "DATABASE_URL is not set in environment. Set DATABASE_URL in backend/.env to connect to Supabase PostgreSQL.",
            "tables": [],
        }

    engine = get_engine()
    if engine is None:
        return {
            "status": "error",
            "connected": False,
            "message": "Could not create database engine.",
            "tables": [],
        }

    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT NOW() as db_time"))
            row = result.fetchone()
            db_time = str(row[0]) if row else None

            # Read-only metadata inspection using SQLAlchemy Inspector
            inspector = inspect(connection)
            table_names = inspector.get_table_names()

            return {
                "status": "connected",
                "connected": True,
                "database_time": db_time,
                "tables_count": len(table_names),
                "tables": sorted(table_names),
            }
    except Exception as exc:
        logger.error(f"Database verification query failed: {exc}")
        return {
            "status": "error",
            "connected": False,
            "error": str(exc),
            "tables": [],
        }
