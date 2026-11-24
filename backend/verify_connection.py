"""Standalone verification script for Supabase PostgreSQL database connectivity.

SAFETY RULES:
- Never prints, logs, or exposes database passwords.
- Never runs DDL, migrations, create_all(), INSERT, UPDATE, or DELETE statements.
- Read-only inspection of metadata and connection ping only.
"""

import sys
from pathlib import Path
from typing import Set

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import inspect, text

from backend.app.config import Settings
from backend.app.database import get_engine, verify_database

EXPECTED_TABLES: Set[str] = {
    "patients",
    "sensor_measurements",
    "clinical_assessments",
    "exacerbations",
    "predictions",
    "alerts",
}


def main() -> int:
    settings = Settings()
    print("=" * 70)
    print("EXACERBALERT SUPABASE CONNECTIVITY VERIFICATION")
    print("=" * 70)

    db_url = settings.DATABASE_URL
    if not db_url:
        print("\n[STATUS: UNCONFIGURED]")
        print("DATABASE_URL is not set in backend/.env or environment.")
        print("Please configure backend/.env with your Supabase connection string:")
        print("  DATABASE_URL=postgresql+psycopg://<user>:<password>@<host>:<port>/<dbname>")
        print("\nSafety check: Zero database modifications performed.")
        return 1

    # Sanitize URL for display (strictly mask password)
    try:
        from urllib.parse import urlparse
        parsed = urlparse(db_url)
        safe_user = parsed.username or "unspecified"
        safe_host = parsed.hostname or "unspecified"
        safe_port = parsed.port or 5432
        safe_db = parsed.path.lstrip("/") or "postgres"
        print(f"\nTarget Database Host: {safe_host}:{safe_port}")
        print(f"Target Database Name: {safe_db}")
        print(f"Target Username:      {safe_user}")
        print(f"Driver Dialect:       {parsed.scheme}")
        print("Password:             [PROTECTED / MASKED]")
    except Exception:
        print("\n[Target URL format parsed safely - credentials masked]")

    print("\nAttempting safe read-only ping via SQLAlchemy (psycopg)...")
    engine = get_engine()
    if engine is None:
        print("[FAILED] Could not construct SQLAlchemy engine.")
        return 1

    try:
        with engine.connect() as conn:
            # 1. Non-destructive ping
            result = conn.execute(text("SELECT NOW() as db_time, current_database() as db_name"))
            row = result.fetchone()
            db_time = row[0] if row else "unknown"
            db_name = row[1] if row else "unknown"
            print(f"[SUCCESS] Connected to database '{db_name}'.")
            print(f"Database Server Time: {db_time}")

            # 2. Inspect table metadata safely
            inspector = inspect(conn)
            existing_tables = set(inspector.get_table_names())
            print(f"\nInspected Tables Count: {len(existing_tables)}")
            print(f"Existing Tables in Public Schema: {sorted(existing_tables)}")

            # 3. Check for the 6 required tables
            missing_tables = EXPECTED_TABLES - existing_tables
            found_tables = EXPECTED_TABLES & existing_tables

            print("\nTable Verification Results:")
            for tbl in sorted(EXPECTED_TABLES):
                status_icon = "✓ ACCESSIBLE" if tbl in existing_tables else "✗ NOT FOUND"
                print(f"  - {tbl:<25} {status_icon}")

            if missing_tables:
                print(f"\n[WARNING] {len(missing_tables)} of 6 expected tables were not found: {missing_tables}")
            else:
                print("\n[CONFIRMED] All 6 expected tables are present and accessible!")

        # 4. Verify verify_database() function used by health endpoint
        health_check = verify_database()
        print(f"\nHealth Endpoint DB Check: connected = {health_check.get('connected')}")
        print("=" * 70)
        return 0 if not missing_tables else 2

    except Exception as exc:
        print(f"\n[CONNECTION ERROR] {exc}")
        print("Verification failed. Please check credentials, network, or pooler status.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
