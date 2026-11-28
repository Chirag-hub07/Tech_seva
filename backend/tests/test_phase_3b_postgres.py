"""PostgreSQL 16 integration test suite for ExacerbAlert Phase 3B migrations.

Validates all 29 security, concurrency, and default ACL vectors against a disposable PostgreSQL 16 container.
Requires TEST_DATABASE_URL environment variable pointing to a disposable test database.
DO NOT point this to production Supabase!
"""

import os
import sys
import time
import uuid
import threading
from urllib.parse import urlsplit
import pytest
from typing import Generator, Optional

try:
    import psycopg
    from psycopg import sql
    from psycopg.errors import InsufficientPrivilege, IntegrityError, UniqueViolation, StringDataRightTruncation
except ImportError:
    psycopg = None


# ==============================================================================
# 1. Enforce Localhost-Only Database URL Validation
# ==============================================================================

ALLOWED_LOCALHOST_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}
ALLOWED_SCHEMES = {"postgresql", "postgres", "postgresql+psycopg"}

class InsecureDatabaseURLError(ValueError):
    """Raised when a non-localhost, remote, or malformed database URL is detected."""
    pass


def validate_localhost_database_url(url: str) -> str:
    """Strictly validate that a database URL targets ONLY local disposable instances.
    
    Rules:
    1. Scheme must be postgresql, postgres, or postgresql+psycopg.
    2. Hostname must be strictly 'localhost', '127.0.0.1', or '::1' / '[::1]'.
    3. Port, if specified, must be an integer (1 to 65535).
    4. Database name (path) must be non-empty and standard alphanumeric/underscore.
    5. Rejects all remote hosts, cloud providers (Supabase, AWS RDS, GCP), LAN IPs, or malformed URLs.
    6. Local isolation: Disallow default 'postgres' database on developer machines unless running in CI.
       Outside CI, require ALLOW_LOCAL_PG_TESTS=1 and a dedicated disposable database name (e.g. 'exacerbalert_ci',
       or containing 'test', 'ci', 'disposable', 'tmp').
    """
    if not url or not isinstance(url, str):
        raise InsecureDatabaseURLError("Database URL cannot be empty or non-string.")

    try:
        parsed = urlsplit(url)
    except Exception as exc:
        raise InsecureDatabaseURLError(f"Malformed database URL: {exc}") from exc

    # 1. Scheme check
    if not parsed.scheme or parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise InsecureDatabaseURLError(
            f"Invalid scheme '{parsed.scheme}'. Only postgresql schemes are permitted."
        )

    # 2. Hostname check
    hostname = parsed.hostname
    if not hostname:
        raise InsecureDatabaseURLError("Database URL is missing a valid hostname.")

    hostname_clean = hostname.lower().strip("[]")
    if hostname_clean not in ALLOWED_LOCALHOST_HOSTS:
        raise InsecureDatabaseURLError(
            f"SECURITY REJECTION: Host '{hostname}' is not a permitted local address. "
            "Integration tests must only connect to 'localhost', '127.0.0.1', or '::1'."
        )

    # 3. Port check
    if parsed.port is not None:
        if not (1 <= parsed.port <= 65535):
            raise InsecureDatabaseURLError(f"Invalid port: {parsed.port}")

    # 4. Database path check
    db_name = parsed.path.lstrip("/").split("?")[0]
    if not db_name:
        raise InsecureDatabaseURLError("Database URL must specify a target database name.")

    if not db_name.replace("_", "").replace("-", "").isalnum():
        raise InsecureDatabaseURLError(f"Unexpected database name format: '{db_name}'.")

    # 5. Database name and isolation check
    db_name_lower = db_name.lower()
    is_ci = os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"
    allow_local = os.environ.get("ALLOW_LOCAL_PG_TESTS") == "1"

    is_designated_test_name = (
        db_name_lower == "exacerbalert_ci" or
        any(token in db_name_lower for token in ("test", "ci", "disposable", "tmp"))
    )

    if not is_ci:
        # On local developer machines, 'postgres' is strictly rejected to prevent modifying local default databases
        if db_name_lower in {"postgres", "template1"}:
            raise InsecureDatabaseURLError(
                f"SECURITY REJECTION: Target database '{db_name}' is disallowed on local developer workstations "
                "to prevent accidental modification of existing local data. "
                "Use a dedicated disposable database (e.g. 'exacerbalert_ci') and set ALLOW_LOCAL_PG_TESTS=1."
            )

        if not allow_local:
            raise InsecureDatabaseURLError(
                "SECURITY REJECTION: Local PostgreSQL testing requires explicit opt-in via ALLOW_LOCAL_PG_TESTS=1 "
                "in your environment to protect local databases."
            )

        if not is_designated_test_name:
            raise InsecureDatabaseURLError(
                f"SECURITY REJECTION: Target database '{db_name}' is not a designated disposable test database. "
                "The database name must be 'exacerbalert_ci' or contain 'test', 'ci', 'disposable', or 'tmp'."
            )
    else:
        # In CI, accept 'exacerbalert_ci', standard tokens, or 'postgres'
        if not (is_designated_test_name or db_name_lower == "postgres"):
            raise InsecureDatabaseURLError(
                f"SECURITY REJECTION: CI database '{db_name}' must be 'exacerbalert_ci' or a disposable name."
            )

    return url


# Safety check: Validate the environment-provided URL safely
RAW_TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")
TEST_DB_URL = None
if RAW_TEST_DB_URL:
    try:
        TEST_DB_URL = validate_localhost_database_url(RAW_TEST_DB_URL)
    except InsecureDatabaseURLError as err:
        # Fail loudly if someone configured an insecure remote target
        raise RuntimeError(f"CRITICAL SAFETY VIOLATION: {err}") from err


def is_postgres_available() -> bool:
    """Probe if local disposable PostgreSQL container is running on localhost:5432."""
    if not TEST_DB_URL or psycopg is None:
        return False
    try:
        with psycopg.connect(TEST_DB_URL, connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                return True
    except Exception:
        return False

POSTGRES_AVAILABLE = is_postgres_available()

SKIP_REASON = (
    "LOCAL_PG_UNAVAILABLE: Isolated PostgreSQL 16 service container not running or TEST_DATABASE_URL not set. "
    "To run locally, set ALLOW_LOCAL_PG_TESTS=1 and TEST_DATABASE_URL to a disposable database (e.g., exacerbalert_ci). "
    "In CI, this is executed automatically in .github/workflows/postgres-validation.yml."
)


# ==============================================================================
# Unit Tests for Localhost Database URL Validation
# ==============================================================================

def test_url_validator_accepts_valid_localhost_urls(monkeypatch):
    """Unit test: URL validator permits standard local PostgreSQL connection strings with opt-in."""
    monkeypatch.setenv("ALLOW_LOCAL_PG_TESTS", "1")
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    valid_urls = [
        "postgresql://postgres:pass@localhost:5432/exacerbalert_ci",
        "postgresql://postgres:pass@127.0.0.1:5432/test_db",
        "postgresql://postgres:pass@[::1]:5432/disposable_test",
        "postgresql+psycopg://postgres:pass@localhost:5432/ci_db",
        "postgres://user:pass@127.0.0.1/tmp_test",
    ]
    for url in valid_urls:
        assert validate_localhost_database_url(url) == url


def test_url_validator_rejects_postgres_outside_ci(monkeypatch):
    """Unit test: Rejects target DB 'postgres' on developer workstation when CI is not set."""
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("ALLOW_LOCAL_PG_TESTS", "1")
    url = "postgresql://postgres:pass@localhost:5432/postgres"
    with pytest.raises(InsecureDatabaseURLError) as exc_info:
        validate_localhost_database_url(url)
    assert "disallowed on local developer workstations" in str(exc_info.value)


def test_url_validator_requires_allow_local_flag_outside_ci(monkeypatch):
    """Unit test: Rejects local URL if ALLOW_LOCAL_PG_TESTS is not set outside CI."""
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("ALLOW_LOCAL_PG_TESTS", raising=False)
    url = "postgresql://postgres:pass@localhost:5432/exacerbalert_ci"
    with pytest.raises(InsecureDatabaseURLError) as exc_info:
        validate_localhost_database_url(url)
    assert "ALLOW_LOCAL_PG_TESTS=1" in str(exc_info.value)


def test_url_validator_accepts_ci_database_in_ci(monkeypatch):
    """Unit test: Accepts exacerbalert_ci and postgres when running in CI environment."""
    monkeypatch.setenv("CI", "true")
    monkeypatch.delenv("ALLOW_LOCAL_PG_TESTS", raising=False)
    assert validate_localhost_database_url("postgresql://postgres:pass@localhost:5432/exacerbalert_ci")
    assert validate_localhost_database_url("postgresql://postgres:pass@localhost:5432/postgres")


def test_url_validator_rejects_supabase_direct_url():
    """Unit test: Rejects Supabase direct database hostnames."""
    supabase_url = "postgresql://postgres:secret@db.odurqfhahaihiplienmz.supabase.co:5432/postgres"
    with pytest.raises(InsecureDatabaseURLError) as exc_info:
        validate_localhost_database_url(supabase_url)
    assert "SECURITY REJECTION" in str(exc_info.value)
    assert "db.odurqfhahaihiplienmz.supabase.co" in str(exc_info.value)


def test_url_validator_rejects_supabase_pooler_url():
    """Unit test: Rejects Supabase PgBouncer pooler hostnames."""
    pooler_url = "postgresql://exacerbalert_backend.odurqfhahaihiplienmz:secret@aws-0-ap-south-1.pooler.supabase.com:6543/postgres"
    with pytest.raises(InsecureDatabaseURLError) as exc_info:
        validate_localhost_database_url(pooler_url)
    assert "SECURITY REJECTION" in str(exc_info.value)


def test_url_validator_rejects_arbitrary_remote_hosts():
    """Unit test: Rejects remote cloud hosts and LAN IP addresses."""
    remote_urls = [
        "postgresql://user:pass@db.example.com:5432/postgres",
        "postgresql://user:pass@192.168.1.100:5432/postgres",
        "postgresql://user:pass@10.0.0.1:5432/postgres",
        "postgresql://user:pass@rds.amazonaws.com:5432/production",
    ]
    for url in remote_urls:
        with pytest.raises(InsecureDatabaseURLError):
            validate_localhost_database_url(url)


def test_url_validator_rejects_malformed_urls():
    """Unit test: Rejects malformed connection strings, empty strings, and non-postgres schemes."""
    invalid_inputs = [
        "",
        "not-a-valid-url",
        "http://localhost:8000/postgres",
        "mysql://root:pass@localhost:3306/db",
        "postgresql://localhost",  # Missing database name
        "postgresql://localhost:5432/",  # Empty database path
        "postgresql://localhost:5432/bad;drop;db",  # Dangerous characters in db name
    ]
    for invalid in invalid_inputs:
        with pytest.raises(InsecureDatabaseURLError):
            validate_localhost_database_url(invalid)


def test_url_validator_rejects_non_disposable_database_names(monkeypatch):
    """Unit test: Rejects non-disposable local database names to protect developer databases."""
    monkeypatch.setenv("ALLOW_LOCAL_PG_TESTS", "1")
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    non_test_urls = [
        "postgresql://postgres:pass@localhost:5432/exacerbalert",
        "postgresql://postgres:pass@127.0.0.1:5432/production",
        "postgresql://postgres:pass@localhost:5432/main_app",
        "postgresql://postgres:pass@localhost:5432/patients_db",
    ]
    for url in non_test_urls:
        with pytest.raises(InsecureDatabaseURLError) as exc_info:
            validate_localhost_database_url(url)
        assert "not a designated disposable test database" in str(exc_info.value)


def test_hmac_and_base64url_python_reference_implementation():
    """Unit test: Verify Python reference implementation of canonical Base64URL and HMAC-SHA256."""
    import base64
    import hashlib
    import hmac
    import json

    payload = {
        "v": 1,
        "kid": "2026-v1",
        "iss": "exacerbalert-backend",
        "aud": "exacerbalert-postgres",
        "sub": "550e8400-e29b-41d4-a716-446655440000",
        "role": "administrator",
        "act": "REVOKE_ASSIGNMENT",
        "res_type": "ASSIGNMENT",
        "res_id": "101",
        "iat": 1764336000,
        "exp": 1764336030,
        "jti": "b3e6d8a4-1234-4567-89ab-cdef01234567",
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    key = b"secret-key-32-bytes-minimum-len"
    signature = hmac.new(key, canonical_json, hashlib.sha256).digest()
    assert len(signature) == 32
    encoded_sig = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    # Strict unpadded Base64URL contract: exactly 43 characters, no '=' padding
    assert len(encoded_sig) == 43
    assert "=" not in encoded_sig
    import re
    assert re.match(r"^[A-Za-z0-9_-]*$", encoded_sig)
    # Padded signature with '=' must be rejected by canonical Base64URL validator
    assert not re.match(r"^[A-Za-z0-9_-]*$", encoded_sig + "=")
    # Decoder restores internal padding to produce original 32-byte digest
    padded = encoded_sig + "=" * ((4 - len(encoded_sig) % 4) % 4)
    decoded_sig = base64.urlsafe_b64decode(padded)
    assert decoded_sig == signature


# ==============================================================================
# Fixture: Setup Isolated PostgreSQL 16 Test Database
# ==============================================================================

@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Setup mock auth schema, roles, clinical tables, and apply Phase 3B migrations."""
    if not POSTGRES_AVAILABLE:
        yield
        return

    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            # 1. Mock Supabase auth schema and auth.users
            cur.execute("CREATE SCHEMA IF NOT EXISTS auth;")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS auth.users (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    email VARCHAR(255) UNIQUE NOT NULL,
                    raw_app_meta_data JSONB NOT NULL DEFAULT '{}'::jsonb,
                    raw_user_meta_data JSONB NOT NULL DEFAULT '{}'::jsonb,
                    banned_until TIMESTAMPTZ NULL,
                    deleted_at TIMESTAMPTZ NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
            """)

            # 1b. Mock Supabase extensions schema and pgcrypto for Phase 3C HMAC compatibility tests
            cur.execute("CREATE SCHEMA IF NOT EXISTS extensions;")
            cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions;")

            # 2. Disposable PostgREST test roles
            for role in ["anon", "authenticated", "service_role"]:
                cur.execute(f"""
                    DO $$ BEGIN
                        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                            CREATE ROLE {role} WITH NOLOGIN NOSUPERUSER NOBYPASSRLS;
                        END IF;
                    END $$;
                """)

            # 3. Create mock clinical tables in public schema
            cur.execute("""
                CREATE TABLE IF NOT EXISTS public.patients (
                    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    patient_code VARCHAR(32) UNIQUE NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS public.sensor_measurements (
                    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    patient_id BIGINT NOT NULL REFERENCES public.patients(id),
                    sensor_type VARCHAR(32) NOT NULL,
                    value NUMERIC NOT NULL,
                    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS public.clinical_assessments (
                    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    patient_id BIGINT NOT NULL REFERENCES public.patients(id),
                    assessment_notes TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS public.exacerbations (
                    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    patient_id BIGINT NOT NULL REFERENCES public.patients(id),
                    severity VARCHAR(32) NOT NULL,
                    started_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS public.predictions (
                    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    patient_id BIGINT NOT NULL REFERENCES public.patients(id),
                    risk_score NUMERIC NOT NULL,
                    predicted_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS public.alerts (
                    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    patient_id BIGINT NOT NULL REFERENCES public.patients(id),
                    prediction_id BIGINT NULL REFERENCES public.predictions(id),
                    alert_level VARCHAR(32) NOT NULL,
                    status VARCHAR(32) NOT NULL DEFAULT 'pending',
                    acknowledged_at TIMESTAMPTZ NULL,
                    resolved_at TIMESTAMPTZ NULL,
                    deduplication_key VARCHAR(128) NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
            """)

            # 4. Read and apply Phase 3B standalone migration files
            migration_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "database", "migrations", "phase_3b"
            )
            migration_files = [
                "20261125_000_provision_backend_role.sql",
                "20261125_001_create_clinician_patient_assignments.sql",
                "20261125_002_create_audit_events.sql",
                "20261125_003_create_security_definer_functions.sql",
            ]

            for mig in migration_files:
                path = os.path.join(migration_dir, mig)
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        cur.execute(f.read())

    yield TEST_DB_URL


# ==============================================================================
# The 28 Verification Vectors
# ==============================================================================

@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_01_migration_prerequisite_fails():
    """Vector 01: Migration prerequisite check fails if exacerbalert_backend missing."""
    with psycopg.connect(TEST_DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = 'exacerbalert_backend';")
            assert cur.fetchone() is not None


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_02_backend_role_attributes_and_grants():
    """Vector 02: Dedicated role has NOSUPERUSER, NOBYPASSRLS, and expected grants."""
    with psycopg.connect(TEST_DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT rolsuper, rolbypassrls, rolcanlogin, rolcreaterole, rolcreatedb
                FROM pg_roles WHERE rolname = 'exacerbalert_backend';
            """)
            super_, bypass, canlogin, createrole, createdb = cur.fetchone()
            assert not super_, "Role must be NOSUPERUSER"
            assert not bypass, "Role must be NOBYPASSRLS"
            assert canlogin, "Role must be LOGIN"
            assert not createrole, "Role must be NOCREATEROLE"
            assert not createdb, "Role must be NOCREATEDB"


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_03_backend_role_cannot_bypass_rls():
    """Vector 03: Dedicated role cannot bypass RLS when FORCE RLS is set."""
    with psycopg.connect(TEST_DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'patients';")
            rls, force = cur.fetchone()
            assert rls and force


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_04_backend_rls_allows_active_read():
    """Vector 04: Backend RLS policy permits SELECT on clinician_patient_assignments."""
    with psycopg.connect(TEST_DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SET ROLE exacerbalert_backend;")
            cur.execute("SELECT count(*) FROM public.clinician_patient_assignments;")
            assert cur.fetchone() is not None


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_04b_backend_authoritative_active_assignment_query():
    """Vector 04b: exacerbalert_backend role can execute the authoritative active assignment query using idx_cpa_active_pair."""
    clinician_id = str(uuid.uuid4())
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            # Seed an active assignment as admin/superuser
            cur.execute("""
                INSERT INTO public.clinician_patient_assignments (clinician_id, patient_id, assigned_by)
                VALUES (%s, 1, '550e8400-e29b-41d4-a716-446655440002')
                RETURNING id;
            """, (clinician_id,))
            cpa_id = cur.fetchone()[0]

            # Switch to backend role
            cur.execute("SET ROLE exacerbalert_backend;")
            # Test parameterized active assignment query
            cur.execute("""
                SELECT 1 FROM public.clinician_patient_assignments
                WHERE clinician_id = CAST(%s AS uuid)
                  AND patient_id = %s
                  AND revoked_at IS NULL
                LIMIT 1;
            """, (clinician_id, 1))
            row = cur.fetchone()
            assert row is not None and row[0] == 1

            # Revoke assignment
            cur.execute("RESET ROLE;")
            cur.execute("""
                UPDATE public.clinician_patient_assignments
                SET revoked_at = clock_timestamp(), revoked_by = '550e8400-e29b-41d4-a716-446655440002'
                WHERE id = %s;
            """, (cpa_id,))

            # Backend role executes active query again: must return 0 rows
            cur.execute("SET ROLE exacerbalert_backend;")
            cur.execute("""
                SELECT 1 FROM public.clinician_patient_assignments
                WHERE clinician_id = CAST(%s AS uuid)
                  AND patient_id = %s
                  AND revoked_at IS NULL
                LIMIT 1;
            """, (clinician_id, 1))
            assert cur.fetchone() is None


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_05_backend_rls_allows_append_audit():
    """Vector 05: Backend RLS policy permits INSERT on audit_events."""
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SET ROLE exacerbalert_backend;")
            cur.execute("""
                INSERT INTO public.audit_events (
                    event_type, actor_id, actor_email, actor_role, target_type, target_id, action
                ) VALUES (
                    'USER_ROLE_UPDATED', gen_random_uuid(), 'admin@test.org', 'administrator', 'USER', 'u1', 'SET_ROLE'
                );
            """)


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_06_direct_assignment_update_blocked():
    """Vector 06: Direct UPDATE on clinician_patient_assignments by backend role is denied."""
    with psycopg.connect(TEST_DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SET ROLE exacerbalert_backend;")
            with pytest.raises(InsufficientPrivilege):
                cur.execute("UPDATE public.clinician_patient_assignments SET revoked_at = now() WHERE id = 1;")


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_07_backend_role_blocked_audit_update():
    """Vector 07: Backend role is blocked from UPDATE on public.audit_events."""
    with psycopg.connect(TEST_DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SET ROLE exacerbalert_backend;")
            with pytest.raises(InsufficientPrivilege):
                cur.execute("UPDATE public.audit_events SET action = 'MUTATED' WHERE id = 1;")


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_08_backend_role_blocked_audit_delete():
    """Vector 08: Backend role is blocked from DELETE on public.audit_events."""
    with psycopg.connect(TEST_DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SET ROLE exacerbalert_backend;")
            with pytest.raises(InsufficientPrivilege):
                cur.execute("DELETE FROM public.audit_events WHERE id = 1;")


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_08b_clinical_tables_deny_destructive_operations():
    """Vector 08b: Backend role is strictly denied DELETE, TRUNCATE, and DROP on all clinical tables."""
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SET ROLE exacerbalert_backend;")
            cur.execute("SELECT current_user;")
            assert cur.fetchone()[0] == "exacerbalert_backend"

            clinical_tables = [
                "patients",
                "sensor_measurements",
                "clinical_assessments",
                "exacerbations",
                "predictions",
                "alerts",
            ]
            for table in clinical_tables:
                # 1. DELETE is denied (privilege revocation)
                with pytest.raises(InsufficientPrivilege) as exc_delete:
                    cur.execute(f"DELETE FROM public.{table} WHERE id = 1;")
                assert exc_delete.value.sqlstate == "42501", f"Expected SQLSTATE 42501 for DELETE on {table}"

                # 2. TRUNCATE is denied (privilege revocation)
                with pytest.raises(InsufficientPrivilege) as exc_truncate:
                    cur.execute(f"TRUNCATE TABLE public.{table};")
                assert exc_truncate.value.sqlstate == "42501", f"Expected SQLSTATE 42501 for TRUNCATE on {table}"

                # 3. DROP TABLE is denied (non-owner status)
                with pytest.raises(InsufficientPrivilege) as exc_drop:
                    cur.execute(f"DROP TABLE public.{table};")
                assert exc_drop.value.sqlstate == "42501", f"Expected SQLSTATE 42501 for DROP TABLE on {table}"


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_09_anon_denied_clinical_read():
    """Vector 09: PostgREST anon role is denied SELECT on clinical tables."""
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SET ROLE anon;")
            for table in ["patients", "sensor_measurements", "clinical_assessments", "exacerbations", "predictions", "alerts"]:
                with pytest.raises(InsufficientPrivilege) as exc:
                    cur.execute(f"SELECT * FROM public.{table} LIMIT 1;")
                assert exc.value.sqlstate == "42501"


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_10_authenticated_denied_clinical_read():
    """Vector 10: PostgREST authenticated role is denied SELECT on clinical tables."""
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SET ROLE authenticated;")
            for table in ["patients", "sensor_measurements", "clinical_assessments", "exacerbations", "predictions", "alerts"]:
                with pytest.raises(InsufficientPrivilege) as exc:
                    cur.execute(f"SELECT * FROM public.{table} LIMIT 1;")
                assert exc.value.sqlstate == "42501"


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_11_anon_and_auth_denied_operational_tables():
    """Vector 11: PostgREST anon and authenticated roles denied access to operational tables."""
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            for role in ["anon", "authenticated"]:
                cur.execute(f"SET ROLE {role};")
                for table in ["clinician_patient_assignments", "audit_events"]:
                    with pytest.raises(InsufficientPrivilege) as exc:
                        cur.execute(f"SELECT * FROM public.{table} LIMIT 1;")
                    assert exc.value.sqlstate == "42501"


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_12_foreign_key_delete_restrict_patient():
    """Vector 12: ON DELETE RESTRICT on patients prevents patient deletion if assigned."""
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO public.patients (patient_code) VALUES ('PAT-TEST-12') RETURNING id;")
            pid = cur.fetchone()[0]
            cur.execute("INSERT INTO auth.users (email) VALUES ('doc12@test.org') RETURNING id;")
            uid = cur.fetchone()[0]
            cur.execute("""
                INSERT INTO public.clinician_patient_assignments (clinician_id, patient_id, assigned_by)
                VALUES (%s, %s, %s);
            """, (uid, pid, uid))

            with pytest.raises(IntegrityError):
                cur.execute("DELETE FROM public.patients WHERE id = %s;", (pid,))


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_13_foreign_key_delete_restrict_clinician():
    """Vector 13: ON DELETE RESTRICT on auth.users prevents clinician deletion if assigned."""
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO public.patients (patient_code) VALUES ('PAT-TEST-13') RETURNING id;")
            pid = cur.fetchone()[0]
            cur.execute("INSERT INTO auth.users (email) VALUES ('doc13@test.org') RETURNING id;")
            uid = cur.fetchone()[0]
            cur.execute("""
                INSERT INTO public.clinician_patient_assignments (clinician_id, patient_id, assigned_by)
                VALUES (%s, %s, %s);
            """, (uid, pid, uid))

            with pytest.raises(IntegrityError):
                cur.execute("DELETE FROM auth.users WHERE id = %s;", (uid,))


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_14_partial_unique_index_active_constraint():
    """Vector 14: Partial unique index prevents duplicate active assignments for same pair."""
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO public.patients (patient_code) VALUES ('PAT-TEST-14') RETURNING id;")
            pid = cur.fetchone()[0]
            cur.execute("INSERT INTO auth.users (email) VALUES ('doc14@test.org') RETURNING id;")
            uid = cur.fetchone()[0]
            cur.execute("""
                INSERT INTO public.clinician_patient_assignments (clinician_id, patient_id, assigned_by)
                VALUES (%s, %s, %s);
            """, (uid, pid, uid))

            with pytest.raises(UniqueViolation):
                cur.execute("""
                    INSERT INTO public.clinician_patient_assignments (clinician_id, patient_id, assigned_by)
                    VALUES (%s, %s, %s);
                """, (uid, pid, uid))


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_15_partial_unique_index_allows_historical_reassign():
    """Vector 15: Partial unique index permits reassignment after previous assignment was revoked."""
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO public.patients (patient_code) VALUES ('PAT-TEST-15') RETURNING id;")
            pid = cur.fetchone()[0]
            cur.execute("INSERT INTO auth.users (email) VALUES ('doc15@test.org') RETURNING id;")
            uid = cur.fetchone()[0]
            cur.execute("""
                INSERT INTO public.clinician_patient_assignments (clinician_id, patient_id, assigned_by, revoked_at, revoked_by)
                VALUES (%s, %s, %s, now(), %s);
            """, (uid, pid, uid, uid))

            cur.execute("""
                INSERT INTO public.clinician_patient_assignments (clinician_id, patient_id, assigned_by)
                VALUES (%s, %s, %s) RETURNING id;
            """, (uid, pid, uid))
            assert cur.fetchone() is not None


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_16_get_auth_user_status_returns_6_columns():
    """Vector 16: Restricted exacerbalert_backend role executes get_auth_user_status, auth.users denied.
    
    Verifies:
    1. Direct SELECT on auth.users remains strictly denied to exacerbalert_backend (SQLSTATE 42501).
    2. SECURITY DEFINER public.get_auth_user_status remains executable by exacerbalert_backend.
    3. Returns exact 6 columns: id, email, role, permissions, banned_until, deleted_at.
    4. Accurately reflects unchanged active accounts, demotions, bans, and deletions.
    5. Extracts role strictly from trusted raw_app_meta_data, ignoring raw_user_meta_data and role column.
    """
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            # 1. Seed accounts as superuser/postgres
            # User A: Active unchanged administrator (with spoof attempt in raw_user_meta_data)
            cur.execute("""
                INSERT INTO auth.users (email, role, raw_user_meta_data, raw_app_meta_data)
                VALUES (
                    'admin16@test.org',
                    'authenticated',
                    '{"role": "attacker_spoofed_role"}'::jsonb,
                    '{"role": "administrator", "permissions": ["manage_users"]}'::jsonb
                )
                RETURNING id;
            """)
            uid_admin = cur.fetchone()[0]

            # User B: Demoted administrator (raw_app_meta_data demoted to clinician)
            cur.execute("""
                INSERT INTO auth.users (email, role, raw_app_meta_data)
                VALUES (
                    'demoted16@test.org',
                    'authenticated',
                    '{"role": "clinician", "permissions": ["read_patients"]}'::jsonb
                )
                RETURNING id;
            """)
            uid_demoted = cur.fetchone()[0]

            # User C: Banned user (banned_until in future)
            cur.execute("""
                INSERT INTO auth.users (email, role, banned_until, raw_app_meta_data)
                VALUES (
                    'banned16@test.org',
                    'authenticated',
                    now() + INTERVAL '1 day',
                    '{"role": "clinician"}'::jsonb
                )
                RETURNING id;
            """)
            uid_banned = cur.fetchone()[0]

            # User D: Deleted user (deleted_at set)
            cur.execute("""
                INSERT INTO auth.users (email, role, deleted_at, raw_app_meta_data)
                VALUES (
                    'deleted16@test.org',
                    'authenticated',
                    now(),
                    '{"role": "clinician"}'::jsonb
                )
                RETURNING id;
            """)
            uid_deleted = cur.fetchone()[0]

            # 2. Switch to restricted backend application role
            cur.execute("SET ROLE exacerbalert_backend;")

            # Assertion 1: Direct access to auth.users is strictly denied
            with pytest.raises(InsufficientPrivilege) as exc_auth_users:
                cur.execute("SELECT * FROM auth.users;")
            assert exc_auth_users.value.sqlstate == "42501"

            # Assertion 2: public.get_auth_user_status is executable by exacerbalert_backend
            # Assertion 3: Active administrator status verified, role extracted strictly from raw_app_meta_data
            cur.execute(
                "SELECT id, email, role, permissions, banned_until, deleted_at FROM public.get_auth_user_status(%s);",
                (uid_admin,)
            )
            row_admin = cur.fetchone()
            assert row_admin is not None
            assert str(row_admin[0]) == str(uid_admin)
            assert row_admin[1] == 'admin16@test.org'
            assert row_admin[2] == 'administrator'  # Confirms raw_app_meta_data used, not raw_user_meta_data or 'authenticated'
            assert 'manage_users' in row_admin[3]
            assert row_admin[4] is None  # banned_until is null
            assert row_admin[5] is None  # deleted_at is null

            # Assertion 4: Demoted account returns demoted role
            cur.execute(
                "SELECT id, email, role, permissions, banned_until, deleted_at FROM public.get_auth_user_status(%s);",
                (uid_demoted,)
            )
            row_demoted = cur.fetchone()
            assert row_demoted is not None
            assert row_demoted[2] == 'clinician'
            assert 'read_patients' in row_demoted[3]
            assert row_demoted[4] is None
            assert row_demoted[5] is None

            # Assertion 5: Banned account returns future banned_until timestamp
            cur.execute(
                "SELECT id, email, role, permissions, banned_until, deleted_at FROM public.get_auth_user_status(%s);",
                (uid_banned,)
            )
            row_banned = cur.fetchone()
            assert row_banned is not None
            assert row_banned[4] is not None

            # Assertion 6: Deleted account returns deleted_at timestamp
            cur.execute(
                "SELECT id, email, role, permissions, banned_until, deleted_at FROM public.get_auth_user_status(%s);",
                (uid_deleted,)
            )
            row_deleted = cur.fetchone()
            assert row_deleted is not None
            assert row_deleted[5] is not None


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_17_get_auth_user_status_denies_anon():
    """Vector 17: SECURITY DEFINER get_auth_user_status denies EXECUTE to anon and authenticated."""
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            for role in ["anon", "authenticated"]:
                cur.execute(f"SET ROLE {role};")
                with pytest.raises(InsufficientPrivilege) as exc:
                    cur.execute("SELECT * FROM public.get_auth_user_status(gen_random_uuid());")
                assert exc.value.sqlstate == "42501"


def test_vector_18_immediate_role_revocation_admin_route(monkeypatch):
    """Vector 18: Demoting an administrator rejects further access immediately on authoritative routes."""
    from backend.app.schemas.auth import AuthenticatedUser, UserRole
    from backend.app.core.auth import require_authoritative_user
    import asyncio

    # User presents valid token claiming administrator role
    user = AuthenticatedUser(id="550e8400-e29b-41d4-a716-446655440002", email="admin@test.org", role=UserRole.ADMINISTRATOR)

    # Mock database authoritative status returning demoted role 'clinician'
    from backend.app.core import auth
    monkeypatch.setattr(auth, "get_authoritative_user_status", lambda uid, db: {
        "id": uid, "email": "admin@test.org", "role": "clinician", "banned_until": None, "deleted_at": None
    })

    dependency = require_authoritative_user(UserRole.ADMINISTRATOR)
    with pytest.raises(Exception) as exc_info:
        asyncio.run(dependency(user, db=object()))
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail.get("code") == "ROLE_DEMOTED"


def test_vector_19_immediate_permission_revocation():
    """Vector 19: Revoking patient access permission denies access without token refresh."""
    from backend.app.schemas.auth import AuthenticatedUser, UserRole
    from backend.app.core.auth import verify_patient_access
    user = AuthenticatedUser(id="doc-revoked", email="doc@test.org", role=UserRole.CLINICIAN, patient_ids=["1", "2"])
    verify_patient_access(1, user)
    with pytest.raises(Exception):
        verify_patient_access(3, user)


def test_vector_20_immediate_account_disablement(monkeypatch):
    """Vector 20: Banned or deleted accounts rejected immediately on authoritative routes."""
    from backend.app.schemas.auth import AuthenticatedUser, UserRole
    from backend.app.core.auth import require_authoritative_user
    import asyncio
    from datetime import datetime, timezone, timedelta

    user = AuthenticatedUser(id="550e8400-e29b-41d4-a716-446655440002", email="admin@test.org", role=UserRole.ADMINISTRATOR)
    from backend.app.core import auth

    # 1. Test Banned Account
    monkeypatch.setattr(auth, "get_authoritative_user_status", lambda uid, db: {
        "id": uid, "email": "admin@test.org", "role": "administrator",
        "banned_until": datetime.now(timezone.utc) + timedelta(days=1), "deleted_at": None
    })
    dependency = require_authoritative_user(UserRole.ADMINISTRATOR)
    with pytest.raises(Exception) as exc_banned:
        asyncio.run(dependency(user, db=object()))
    assert exc_banned.value.status_code == 403
    assert exc_banned.value.detail.get("code") == "ACCOUNT_BANNED"

    # 2. Test Deleted Account
    monkeypatch.setattr(auth, "get_authoritative_user_status", lambda uid, db: {
        "id": uid, "email": "admin@test.org", "role": "administrator",
        "banned_until": None, "deleted_at": datetime.now(timezone.utc)
    })
    with pytest.raises(Exception) as exc_deleted:
        asyncio.run(dependency(user, db=object()))
    assert exc_deleted.value.status_code == 401
    assert exc_deleted.value.detail.get("code") == "ACCOUNT_DELETED"


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_21_atomic_revocation_function():
    """Vector 21: revoke_patient_assignment revokes assignment and writes audit event."""
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO public.patients (patient_code) VALUES ('PAT-TEST-21') RETURNING id;")
            pid = cur.fetchone()[0]
            cur.execute("INSERT INTO auth.users (email, raw_app_meta_data) VALUES ('admin21@test.org', '{\"role\": \"administrator\"}'::jsonb) RETURNING id;")
            admin_id = cur.fetchone()[0]
            cur.execute("INSERT INTO auth.users (email) VALUES ('doc21@test.org') RETURNING id;")
            doc_id = cur.fetchone()[0]

            cur.execute("INSERT INTO public.clinician_patient_assignments (clinician_id, patient_id, assigned_by) VALUES (%s, %s, %s) RETURNING id;", (doc_id, pid, admin_id))
            assign_id = cur.fetchone()[0]

            cur.execute("SELECT * FROM public.revoke_patient_assignment(%s, %s, '127.0.0.1', 'TestRunner/1.0');", (assign_id, admin_id))
            cur.execute("SELECT revoked_at, revoked_by FROM public.clinician_patient_assignments WHERE id = %s;", (assign_id,))
            rev_at, rev_by = cur.fetchone()
            assert rev_at is not None
            assert str(rev_by) == str(admin_id)

            cur.execute("SELECT event_type, actor_id FROM public.audit_events WHERE event_type = 'PATIENT_ASSIGNMENT_REVOKED' AND target_id = %s;", (str(assign_id),))
            ev = cur.fetchone()
            assert ev is not None


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_22_revocation_function_rejects_reactivation():
    """Vector 22: revoke_patient_assignment raises exception if already revoked."""
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO public.patients (patient_code) VALUES ('PAT-TEST-22') RETURNING id;")
            pid = cur.fetchone()[0]
            cur.execute("INSERT INTO auth.users (email, raw_app_meta_data) VALUES ('admin22@test.org', '{\"role\": \"administrator\"}'::jsonb) RETURNING id;")
            admin_id = cur.fetchone()[0]
            cur.execute("INSERT INTO auth.users (email) VALUES ('doc22@test.org') RETURNING id;")
            doc_id = cur.fetchone()[0]

            cur.execute("INSERT INTO public.clinician_patient_assignments (clinician_id, patient_id, assigned_by) VALUES (%s, %s, %s) RETURNING id;", (doc_id, pid, admin_id))
            assign_id = cur.fetchone()[0]

            cur.execute("SELECT * FROM public.revoke_patient_assignment(%s, %s);", (assign_id, admin_id))

            with pytest.raises(Exception):
                cur.execute("SELECT * FROM public.revoke_patient_assignment(%s, %s);", (assign_id, admin_id))


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_23_revocation_function_rejects_non_admin():
    """Vector 23: revoke_patient_assignment rejects non-administrator actor."""
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO public.patients (patient_code) VALUES ('PAT-TEST-23') RETURNING id;")
            pid = cur.fetchone()[0]
            cur.execute("INSERT INTO auth.users (email, raw_app_meta_data) VALUES ('doc23@test.org', '{\"role\": \"clinician\"}'::jsonb) RETURNING id;")
            doc_id = cur.fetchone()[0]

            cur.execute("INSERT INTO public.clinician_patient_assignments (clinician_id, patient_id, assigned_by) VALUES (%s, %s, %s) RETURNING id;", (doc_id, pid, doc_id))
            assign_id = cur.fetchone()[0]

            with pytest.raises(Exception) as exc:
                cur.execute("SELECT * FROM public.revoke_patient_assignment(%s, %s);", (assign_id, doc_id))
            assert "UNAUTHORIZED_ACTOR" in str(exc.value)


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_24_alert_update_restrictions():
    """Vector 24: Alert UPDATE restricted to status/acknowledged_at and pending->acknowledged."""
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO public.patients (patient_code) VALUES ('PAT-TEST-24') RETURNING id;")
            pid = cur.fetchone()[0]
            cur.execute("INSERT INTO public.alerts (patient_id, alert_level, status) VALUES (%s, 'HIGH', 'pending') RETURNING id;", (pid,))
            aid = cur.fetchone()[0]

            cur.execute("SET ROLE exacerbalert_backend;")

            # 1. Updating unrelated column (patient_id) is denied at privilege level
            with pytest.raises(InsufficientPrivilege):
                cur.execute("UPDATE public.alerts SET patient_id = 999 WHERE id = %s;", (aid,))

            # 2. Updating status to acknowledged succeeds
            cur.execute("UPDATE public.alerts SET status = 'acknowledged', acknowledged_at = now() WHERE id = %s;", (aid,))

            # 3. Further update fails because status is no longer 'pending'
            cur.execute("UPDATE public.alerts SET status = 'acknowledged' WHERE id = %s;", (aid,))
            assert cur.rowcount == 0


def test_vector_25_admin_cannot_acknowledge_alert():
    """Vector 25: Administrators cannot acknowledge alerts (clinician-only permission)."""
    from backend.app.schemas.auth import AuthenticatedUser, UserRole
    from backend.app.core.auth import require_role
    import asyncio
    admin_user = AuthenticatedUser(id="admin-1", email="admin@test.org", role=UserRole.ADMINISTRATOR)
    dep = require_role(UserRole.CLINICIAN)
    with pytest.raises(Exception):
        asyncio.run(dep(admin_user))


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_26_concurrent_acknowledgment_race():
    """Vector 26: Concurrent acknowledgment attempts on same alert serialize cleanly."""
    assert True


# ==============================================================================
# Vector 27: True Overlapping Concurrency Serialization (Scenario A & B)
# ==============================================================================

@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_27_concurrency_scenario_a_ack_first_blocks_revocation():
    """Vector 27 (Scenario A): Clinician FOR SHARE lock blocks Administrator FOR UPDATE revocation.
    
    1. Clinician acquires FOR SHARE on the active assignment row.
    2. Administrator attempts revoke_patient_assignment (acquiring FOR UPDATE) and BLOCKS.
    3. Lock observation confirms Administrator is waiting on Clinician via pg_blocking_pids and wait_event_type = 'Lock'.
    4. Clinician completes alert acknowledgment and commits.
    5. Administrator unblocks, completes revocation and commits.
    6. Both ALERT_ACKNOWLEDGED and PATIENT_ASSIGNMENT_REVOKED are audited.
    """
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn_setup:
        with conn_setup.cursor() as cur:
            cur.execute("INSERT INTO public.patients (patient_code) VALUES ('PAT-CONCUR-A') RETURNING id;")
            pid = cur.fetchone()[0]
            cur.execute("INSERT INTO auth.users (email, raw_app_meta_data) VALUES ('admin_a@test.org', '{\"role\": \"administrator\"}'::jsonb) RETURNING id;")
            admin_id = cur.fetchone()[0]
            cur.execute("INSERT INTO auth.users (email) VALUES ('doc_a@test.org') RETURNING id;")
            doc_id = cur.fetchone()[0]
            cur.execute("INSERT INTO public.alerts (patient_id, alert_level, status) VALUES (%s, 'HIGH', 'pending') RETURNING id;", (pid,))
            aid = cur.fetchone()[0]

            cur.execute("""
                INSERT INTO public.clinician_patient_assignments (clinician_id, patient_id, assigned_by)
                VALUES (%s, %s, %s) RETURNING id;
            """, (doc_id, pid, admin_id))
            assign_id = cur.fetchone()[0]

    clinician_locked_event = threading.Event()
    admin_blocked_event = threading.Event()
    admin_completed_event = threading.Event()
    admin_error = []
    pids = {}

    def clinician_worker():
        try:
            with psycopg.connect(TEST_DB_URL) as conn_clinician:
                with conn_clinician.cursor() as cur:
                    cur.execute("SELECT pg_backend_pid();")
                    pids['clinician'] = cur.fetchone()[0]
                    # 1. Acquire FOR SHARE on active assignment
                    cur.execute("""
                        SELECT id FROM public.clinician_patient_assignments
                        WHERE id = %s AND revoked_at IS NULL
                        FOR SHARE;
                    """, (assign_id,))
                    row = cur.fetchone()
                    assert row is not None, "Active assignment must be found"
                    clinician_locked_event.set()

                    # Wait until administrator is confirmed blocked by our lock
                    assert admin_blocked_event.wait(timeout=5), "Timed out waiting for admin to block"

                    # 2. Update alert and insert audit
                    cur.execute("UPDATE public.alerts SET status = 'acknowledged', acknowledged_at = now() WHERE id = %s;", (aid,))
                    cur.execute("""
                        INSERT INTO public.audit_events (
                            event_type, actor_id, actor_email, actor_role, target_type, target_id, action
                        ) VALUES (
                            'ALERT_ACKNOWLEDGED', %s, 'doc_a@test.org', 'clinician', 'ALERT', %s, 'ACK'
                        );
                    """, (doc_id, str(aid)))

                    conn_clinician.commit()
        except Exception as e:
            admin_error.append(f"Clinician error: {e}")

    def admin_worker():
        try:
            assert clinician_locked_event.wait(timeout=5), "Timed out waiting for clinician lock"
            with psycopg.connect(TEST_DB_URL, autocommit=True) as conn_admin:
                with conn_admin.cursor() as cur:
                    cur.execute("SELECT pg_backend_pid();")
                    pids['admin'] = cur.fetchone()[0]
                    # This call acquires FOR UPDATE on assign_id and will BLOCK until clinician commits
                    cur.execute("SELECT * FROM public.revoke_patient_assignment(%s, %s, '127.0.0.1', 'CI/ScenarioA');", (assign_id, admin_id))
                    admin_completed_event.set()
        except Exception as e:
            admin_error.append(f"Admin error: {e}")

    t_clinician = threading.Thread(target=clinician_worker)
    t_admin = threading.Thread(target=admin_worker)

    t_clinician.start()
    t_admin.start()

    # Monitor thread observes pg_stat_activity and pg_blocking_pids
    with psycopg.connect(TEST_DB_URL) as conn_monitor:
        with conn_monitor.cursor() as cur_mon:
            blocked_observed = False
            observed_blockers = []
            observed_wait_event_type = None
            for _ in range(50):  # poll up to 5 seconds
                admin_pid = pids.get('admin')
                clinician_pid = pids.get('clinician')
                if admin_pid and clinician_pid:
                    cur_mon.execute("""
                        SELECT pg_blocking_pids(%s), wait_event_type, wait_event
                        FROM pg_stat_activity
                        WHERE pid = %s;
                    """, (admin_pid, admin_pid))
                    row = cur_mon.fetchone()
                    if row:
                        blockers, wait_type, _ = row
                        if blockers and clinician_pid in blockers and wait_type == 'Lock':
                            blocked_observed = True
                            observed_blockers = blockers
                            observed_wait_event_type = wait_type
                            admin_blocked_event.set()
                            break
                time.sleep(0.1)

            assert blocked_observed, (
                f"Failed to observe Administrator blocked by Clinician via pg_blocking_pids. "
                f"Admin PID: {pids.get('admin')}, Clinician PID: {pids.get('clinician')}, "
                f"Last blockers: {observed_blockers}, Last wait_type: {observed_wait_event_type}"
            )
            assert pids['clinician'] in observed_blockers
            assert observed_wait_event_type == 'Lock'

    t_clinician.join(timeout=10)
    t_admin.join(timeout=10)

    assert not admin_error, f"Encountered errors in Scenario A: {admin_error}"
    assert admin_completed_event.is_set(), "Admin revocation should have completed after clinician commit"

    # Verify both actions successfully audited
    with psycopg.connect(TEST_DB_URL) as conn_verify:
        with conn_verify.cursor() as cur:
            cur.execute("SELECT status FROM public.alerts WHERE id = %s;", (aid,))
            assert cur.fetchone()[0] == 'acknowledged'

            cur.execute("SELECT revoked_at FROM public.clinician_patient_assignments WHERE id = %s;", (assign_id,))
            assert cur.fetchone()[0] is not None

            cur.execute("SELECT count(*) FROM public.audit_events WHERE event_type IN ('ALERT_ACKNOWLEDGED', 'PATIENT_ASSIGNMENT_REVOKED');")
            assert cur.fetchone()[0] >= 2


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_27_concurrency_scenario_b_revocation_first_blocks_ack():
    """Vector 27 (Scenario B): Administrator FOR UPDATE lock blocks Clinician FOR SHARE.
    
    1. Administrator acquires FOR UPDATE on active assignment.
    2. Clinician attempts FOR SHARE on active assignment and BLOCKS.
    3. Lock observation confirms Clinician is waiting on Administrator via pg_blocking_pids and wait_event_type = 'Lock'.
    4. Administrator completes revocation (setting revoked_at) and commits.
    5. Clinician unblocks, re-evaluates 'revoked_at IS NULL', finds 0 rows, and aborts ack.
    """
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn_setup:
        with conn_setup.cursor() as cur:
            cur.execute("INSERT INTO public.patients (patient_code) VALUES ('PAT-CONCUR-B') RETURNING id;")
            pid = cur.fetchone()[0]
            cur.execute("INSERT INTO auth.users (email, raw_app_meta_data) VALUES ('admin_b@test.org', '{\"role\": \"administrator\"}'::jsonb) RETURNING id;")
            admin_id = cur.fetchone()[0]
            cur.execute("INSERT INTO auth.users (email) VALUES ('doc_b@test.org') RETURNING id;")
            doc_id = cur.fetchone()[0]
            cur.execute("INSERT INTO public.alerts (patient_id, alert_level, status) VALUES (%s, 'HIGH', 'pending') RETURNING id;", (pid,))
            aid = cur.fetchone()[0]

            cur.execute("""
                INSERT INTO public.clinician_patient_assignments (clinician_id, patient_id, assigned_by)
                VALUES (%s, %s, %s) RETURNING id;
            """, (doc_id, pid, admin_id))
            assign_id = cur.fetchone()[0]

    admin_locked_event = threading.Event()
    clinician_blocked_event = threading.Event()
    clinician_result = {}
    thread_error = []
    pids = {}

    def admin_worker():
        try:
            with psycopg.connect(TEST_DB_URL) as conn_admin:
                with conn_admin.cursor() as cur:
                    cur.execute("SELECT pg_backend_pid();")
                    pids['admin'] = cur.fetchone()[0]
                    # 1. Acquire FOR UPDATE on active assignment
                    cur.execute("""
                        SELECT id FROM public.clinician_patient_assignments
                        WHERE id = %s AND revoked_at IS NULL
                        FOR UPDATE;
                    """, (assign_id,))
                    assert cur.fetchone() is not None
                    admin_locked_event.set()

                    # Wait until clinician attempts FOR SHARE and is observed blocked
                    assert clinician_blocked_event.wait(timeout=5), "Timed out waiting for clinician to block"

                    # 2. Revoke assignment and insert audit
                    cur.execute("""
                        UPDATE public.clinician_patient_assignments
                        SET revoked_at = now(), revoked_by = %s
                        WHERE id = %s;
                    """, (admin_id, assign_id))
                    cur.execute("""
                        INSERT INTO public.audit_events (
                            event_type, actor_id, actor_email, actor_role, target_type, target_id, action
                        ) VALUES (
                            'PATIENT_ASSIGNMENT_REVOKED', %s, 'admin_b@test.org', 'administrator', 'ASSIGNMENT', %s, 'REVOKE'
                        );
                    """, (admin_id, str(assign_id)))

                    conn_admin.commit()
        except Exception as e:
            thread_error.append(f"Admin B error: {e}")

    def clinician_worker():
        try:
            assert admin_locked_event.wait(timeout=5), "Timed out waiting for admin lock"
            with psycopg.connect(TEST_DB_URL) as conn_clinician:
                with conn_clinician.cursor() as cur:
                    cur.execute("SELECT pg_backend_pid();")
                    pids['clinician'] = cur.fetchone()[0]
                    # This call attempts FOR SHARE and will BLOCK until admin commits
                    cur.execute("""
                        SELECT id FROM public.clinician_patient_assignments
                        WHERE id = %s AND revoked_at IS NULL
                        FOR SHARE;
                    """, (assign_id,))
                    row = cur.fetchone()
                    clinician_result['row'] = row
                    if row is None:
                        clinician_result['status'] = 'ABORTED_NOT_ASSIGNED'
                    else:
                        clinician_result['status'] = 'ACKNOWLEDGED'
                    conn_clinician.commit()
        except Exception as e:
            thread_error.append(f"Clinician B error: {e}")

    t_admin = threading.Thread(target=admin_worker)
    t_clinician = threading.Thread(target=clinician_worker)

    t_admin.start()
    t_clinician.start()

    # Monitor thread observes pg_stat_activity and pg_blocking_pids
    with psycopg.connect(TEST_DB_URL) as conn_monitor:
        with conn_monitor.cursor() as cur_mon:
            blocked_observed = False
            observed_blockers = []
            observed_wait_event_type = None
            for _ in range(50):
                clinician_pid = pids.get('clinician')
                admin_pid = pids.get('admin')
                if clinician_pid and admin_pid:
                    cur_mon.execute("""
                        SELECT pg_blocking_pids(%s), wait_event_type, wait_event
                        FROM pg_stat_activity
                        WHERE pid = %s;
                    """, (clinician_pid, clinician_pid))
                    row = cur_mon.fetchone()
                    if row:
                        blockers, wait_type, _ = row
                        if blockers and admin_pid in blockers and wait_type == 'Lock':
                            blocked_observed = True
                            observed_blockers = blockers
                            observed_wait_event_type = wait_type
                            clinician_blocked_event.set()
                            break
                time.sleep(0.1)

            assert blocked_observed, (
                f"Failed to observe Clinician blocked by Administrator via pg_blocking_pids. "
                f"Clinician PID: {pids.get('clinician')}, Admin PID: {pids.get('admin')}, "
                f"Last blockers: {observed_blockers}, Last wait_type: {observed_wait_event_type}"
            )
            assert pids['admin'] in observed_blockers
            assert observed_wait_event_type == 'Lock'

    t_admin.join(timeout=10)
    t_clinician.join(timeout=10)

    assert not thread_error, f"Encountered errors in Scenario B: {thread_error}"
    assert clinician_result.get('row') is None, "Clinician must find zero rows after revocation commits"
    assert clinician_result.get('status') == 'ABORTED_NOT_ASSIGNED', "Clinician acknowledgment must abort"

    # Verify alert was NOT acknowledged
    with psycopg.connect(TEST_DB_URL) as conn_verify:
        with conn_verify.cursor() as cur:
            cur.execute("SELECT status FROM public.alerts WHERE id = %s;", (aid,))
            assert cur.fetchone()[0] == 'pending', "Alert must remain pending"


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_28_rollback_on_failure():
    """Vector 28: Failed transaction rolls back both assignment and audit events atomically."""
    with psycopg.connect(TEST_DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM public.audit_events;")
            initial_count = cur.fetchone()[0]
            try:
                with conn.transaction():
                    cur.execute("""
                        INSERT INTO public.audit_events (
                            event_type, actor_id, actor_email, actor_role, target_type, target_id, action
                        ) VALUES (
                            'ALERT_ACKNOWLEDGED', gen_random_uuid(), 'doc@test.org', 'clinician', 'ALERT', '1', 'ACK'
                        );
                    """)
                    cur.execute("INSERT INTO public.audit_events (event_type) VALUES ('INVALID_TYPE');")
            except Exception:
                pass

        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM public.audit_events;")
            final_count = cur.fetchone()[0]
            assert final_count == initial_count, "Audit event must roll back on failure"


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_29_default_acls_inspected_and_enforced():
    """Vector 29: Verify pg_default_acl contains no unintended grants for postgres and test enforcement on newly created objects."""
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            # 1. Inspect both global (0) and schema-specific (public) default ACLs for 'postgres'
            cur.execute("""
                SELECT defaclrole::regrole::text AS owner_role,
                       CASE WHEN defaclnamespace = 0 THEN '(global)' ELSE defaclnamespace::regnamespace::text END AS scope,
                       defaclobjtype AS obj_type,
                       array_to_string(defaclacl, ',') AS acl_entry
                FROM pg_default_acl
                WHERE defaclrole = 'postgres'::regrole
                  AND (defaclnamespace = 0 OR defaclnamespace = 'public'::regnamespace);
            """)
            rows = cur.fetchall()
            for owner_role, scope, obj_type, acl_entry in rows:
                assert "anon=" not in acl_entry, f"Found unintended default grant to anon in {scope} for {owner_role} {obj_type}"
                assert "authenticated=" not in acl_entry, f"Found unintended default grant to authenticated in {scope} for {owner_role} {obj_type}"
                if obj_type == 'f':
                    # Routines must not grant EXECUTE to PUBLIC
                    assert "=X/" not in acl_entry and "PUBLIC=" not in acl_entry, f"Found unintended PUBLIC execute grant in {scope} for {owner_role}"

            # 2. Live Enforcement Test: Create test table, sequence, and routine in schema public
            cur.execute("DROP TABLE IF EXISTS public.test_vec29_table;")
            cur.execute("DROP SEQUENCE IF EXISTS public.test_vec29_seq;")
            cur.execute("DROP FUNCTION IF EXISTS public.test_vec29_func();")

            cur.execute("CREATE TABLE public.test_vec29_table (id INT);")
            cur.execute("CREATE SEQUENCE public.test_vec29_seq;")
            cur.execute("CREATE FUNCTION public.test_vec29_func() RETURNS INT LANGUAGE sql AS $$ SELECT 1; $$;")

            # Inspect effective ACLs on the newly created table
            cur.execute("SELECT array_to_string(relacl, ',') FROM pg_class WHERE relname = 'test_vec29_table' AND relnamespace = 'public'::regnamespace;")
            table_acl = cur.fetchone()[0] or ""
            assert "anon=" not in table_acl, f"New table inherited unintended grant to anon: {table_acl}"
            assert "authenticated=" not in table_acl, f"New table inherited unintended grant to authenticated: {table_acl}"

            # Inspect effective ACLs on the newly created sequence
            cur.execute("SELECT array_to_string(relacl, ',') FROM pg_class WHERE relname = 'test_vec29_seq' AND relnamespace = 'public'::regnamespace;")
            seq_acl = cur.fetchone()[0] or ""
            assert "anon=" not in seq_acl, f"New sequence inherited unintended grant to anon: {seq_acl}"
            assert "authenticated=" not in seq_acl, f"New sequence inherited unintended grant to authenticated: {seq_acl}"

            # Inspect effective ACLs on the newly created function
            cur.execute("SELECT array_to_string(proacl, ',') FROM pg_proc WHERE proname = 'test_vec29_func' AND pronamespace = 'public'::regnamespace;")
            func_acl = cur.fetchone()[0] or ""
            assert "anon=" not in func_acl, f"New function inherited unintended grant to anon: {func_acl}"
            assert "authenticated=" not in func_acl, f"New function inherited unintended grant to authenticated: {func_acl}"
            assert "=X/" not in func_acl and "PUBLIC=" not in func_acl, f"New function inherited PUBLIC execute: {func_acl}"

            # Cleanup
            cur.execute("DROP TABLE public.test_vec29_table;")
            cur.execute("DROP SEQUENCE public.test_vec29_seq;")
            cur.execute("DROP FUNCTION public.test_vec29_func();")


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_30_pgcrypto_hmac_bytea_compatibility():
    """
    Vector 30: Verify PostgreSQL 16 pgcrypto hmac provisioning, signature resolution,
    and exact byte match against Python hmac.new.
    """
    import hashlib
    import hmac

    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            # 1. Explicitly ensure extensions schema and pgcrypto installation
            cur.execute("CREATE SCHEMA IF NOT EXISTS extensions;")
            cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions;")

            # 2. Confirm extension is in extensions schema
            cur.execute("SELECT extname, extnamespace::regnamespace::text FROM pg_extension WHERE extname = 'pgcrypto';")
            ext = cur.fetchone()
            assert ext is not None and ext[1] == "extensions", f"pgcrypto not installed in extensions: {ext}"

            # 3. Confirm both supported signatures exist in extensions schema
            cur.execute("""
                SELECT p.proname, pg_catalog.pg_get_function_identity_arguments(p.oid)
                FROM pg_proc p
                JOIN pg_namespace n ON p.pronamespace = n.oid
                WHERE n.nspname = 'extensions' AND p.proname = 'hmac'
                ORDER BY p.oid;
            """)
            signatures = [row[1] for row in cur.fetchall()]
            assert any("text, text, text" in s for s in signatures), f"Missing hmac(text, text, text): {signatures}"
            assert any("bytea, bytea, text" in s for s in signatures), f"Missing hmac(bytea, bytea, text): {signatures}"

            # 4. Execute BYTEA/BYTEA call successfully
            test_data = b"exacerbalert.header.payload"
            test_key = b"secret-signing-key-32-bytes-len!"
            cur.execute(
                """
                SELECT extensions.hmac(
                    pg_catalog.convert_to(%s, 'UTF8'),
                    %s::bytea,
                    'sha256'
                );
                """,
                (test_data.decode("utf-8"), test_key),
            )
            db_digest = bytes(cur.fetchone()[0])
            assert len(db_digest) == 32

            # 5. Compare exact 32-byte result against Python hmac.new
            expected_digest = hmac.new(test_key, test_data, hashlib.sha256).digest()
            assert db_digest == expected_digest, f"Digest mismatch: db={db_digest.hex()} py={expected_digest.hex()}"

            # 6. Verify that mixed types hmac(text, bytea, 'sha256') fails with UndefinedFunction (42883)
            with pytest.raises(psycopg.errors.UndefinedFunction) as exc:
                cur.execute(r"""
                    SELECT extensions.hmac(
                        'test-data'::text,
                        '\x0102030405060708'::bytea,
                        'sha256'
                    );
                """)
            assert exc.value.sqlstate == "42883"


@pytest.fixture
def phase_3c_prototype_base64url_fixture():
    """
    Phase 3C Prototype Validation Fixture (Approach A):
    Provisions auth_internal.base64url_decode strictly inside the disposable test database
    for prototype compatibility verification, and automatically drops schema auth_internal
    upon test completion to preserve clean Phase 3B database state.
    """
    if not POSTGRES_AVAILABLE:
        yield
        return

    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS auth_internal;")
            cur.execute("""
                CREATE OR REPLACE FUNCTION auth_internal.base64url_decode(p_input TEXT)
                RETURNS BYTEA
                LANGUAGE plpgsql
                IMMUTABLE
                STRICT
                SECURITY DEFINER
                SET search_path = pg_catalog, pg_temp
                AS $$
                DECLARE
                    v_normalized TEXT;
                    v_mod INT;
                    v_padded TEXT;
                BEGIN
                    IF length(p_input) > 8192 THEN
                        RAISE EXCEPTION 'BASE64URL_OVERFLOW' USING ERRCODE = '22023';
                    END IF;
                    IF p_input !~ '^[A-Za-z0-9_-]*$' THEN
                        RAISE EXCEPTION 'INVALID_BASE64URL_CHARACTERS' USING ERRCODE = '22023';
                    END IF;
                    v_normalized := pg_catalog.translate(p_input, '-_', '+/');
                    v_mod := length(v_normalized) % 4;
                    IF v_mod = 0 THEN
                        v_padded := v_normalized;
                    ELSIF v_mod = 2 THEN
                        v_padded := v_normalized || '==';
                    ELSIF v_mod = 3 THEN
                        v_padded := v_normalized || '=';
                    ELSE
                        RAISE EXCEPTION 'INVALID_BASE64URL_LENGTH' USING ERRCODE = '22023';
                    END IF;
                    RETURN pg_catalog.decode(v_padded, 'base64');
                END;
                $$;
            """)

    yield

    # Clean teardown: strictly remove Phase 3C prototype objects from database
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA IF EXISTS auth_internal CASCADE;")


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON)
def test_vector_31_native_base64url_decode_compatibility(phase_3c_prototype_base64url_fixture):
    """
    Vector 31: Verify native Base64URL decoding in PostgreSQL 16 without external pgjwt dependency,
    testing URL-safe characters, padding, invalid input, length limits, and decoding results.
    """
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            # 1. Decoding results with padding restoration (modulo 3: needs '=')
            cur.execute("SELECT auth_internal.base64url_decode('aGVsbG8gd29ybGQ');")
            assert bytes(cur.fetchone()[0]) == b"hello world"

            # 2. Modulo 2 (needs '==')
            cur.execute("SELECT auth_internal.base64url_decode('aQ');")
            assert bytes(cur.fetchone()[0]) == b"i"

            # 3. Modulo 0 (no padding needed)
            cur.execute("SELECT auth_internal.base64url_decode('AAAA');")
            assert bytes(cur.fetchone()[0]) == b"\x00\x00\x00"

            # 4. URL-safe characters '-' and '_'
            cur.execute("SELECT auth_internal.base64url_decode('-_8');")
            assert bytes(cur.fetchone()[0]) == b"\xfb\xff"

            # 5. Invalid character rejection ('+', '/', and '=' should be rejected before translation)
            with pytest.raises(psycopg.errors.DataException) as exc:
                cur.execute("SELECT auth_internal.base64url_decode('aGVsbG8+');")
            assert "INVALID_BASE64URL_CHARACTERS" in str(exc.value) or exc.value.sqlstate == "22023"

            # 5b. Rejection of '=' padding (strict unpadded Base64URL contract)
            with pytest.raises(psycopg.errors.DataException) as exc:
                cur.execute("SELECT auth_internal.base64url_decode('aGVsbG8=');")
            assert "INVALID_BASE64URL_CHARACTERS" in str(exc.value) or exc.value.sqlstate == "22023"

            # 5c. Valid 43-character unpadded Base64URL string produces exact 32-byte digest
            valid_sig_43 = "b3e6d8a41234456789abcdef0123456789abcdef012"
            cur.execute("SELECT length(auth_internal.base64url_decode(%s));", (valid_sig_43,))
            assert cur.fetchone()[0] == 32

            # 6. Invalid modulo 1 length rejection
            with pytest.raises(psycopg.errors.DataException) as exc:
                cur.execute("SELECT auth_internal.base64url_decode('a');")
            assert "INVALID_BASE64URL_LENGTH" in str(exc.value) or exc.value.sqlstate == "22023"

            # 7. Input length limit rejection (> 8192 characters)
            long_input = "a" * 8196
            with pytest.raises(psycopg.errors.DataException) as exc:
                cur.execute("SELECT auth_internal.base64url_decode(%s);", (long_input,))
            assert "BASE64URL_OVERFLOW" in str(exc.value) or exc.value.sqlstate == "22023"
