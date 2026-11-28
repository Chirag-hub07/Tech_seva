"""Supabase JWT authentication and role-based access control (RBAC) engine."""

import logging
import time
from typing import Any, Dict, List, Optional, Union
import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from jwt import PyJWKClient, PyJWKClientError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from sqlalchemy.orm import Session
from backend.app.config import settings
from backend.app.database import get_db
from backend.app.schemas.auth import AuthenticatedUser, UserRole

logger = logging.getLogger("backend.app.auth")

oauth2_bearer = HTTPBearer(
    auto_error=False,
    description="Supabase Auth access token in Authorization: Bearer <token> format",
)


class SupabaseJWTVerifier:
    """Production-grade Supabase JWT verifier with asymmetric JWKS key rotation."""

    def __init__(
        self,
        jwks_url: Optional[str] = None,
        issuer: Optional[str] = None,
        audience: Optional[str] = None,
        algorithms: Optional[List[str]] = None,
        cache_ttl: int = 3600,
    ) -> None:
        self.jwks_url = jwks_url or settings.effective_jwks_url
        self.issuer = issuer or settings.effective_jwt_issuer
        self.audience = audience or settings.SUPABASE_JWT_AUDIENCE
        self.algorithms = algorithms or settings.AUTH_ALGORITHMS
        self.cache_ttl = cache_ttl

        # PyJWKClient with built-in caching and rotation support
        self._jwks_client: Optional[PyJWKClient] = None
        self._test_signing_keys: Dict[str, Any] = {}
        self._initialize_jwks_client()

    def _initialize_jwks_client(self) -> None:
        """Initialize or refresh the PyJWKClient instance."""
        try:
            self._jwks_client = PyJWKClient(
                uri=self.jwks_url,
                cache_keys=True,
                max_cached_keys=16,
                cache_jwk_set=True,
                lifespan=self.cache_ttl,
            )
            logger.info(f"Supabase JWKS client initialized: {self.jwks_url}")
        except Exception as exc:
            logger.warning(f"Failed to initialize JWKS client for {self.jwks_url}: {exc}")
            self._jwks_client = None

    def register_test_key(self, kid: str, public_key: Any) -> None:
        """Register an isolated test key for offline unit tests and mocking."""
        self._test_signing_keys[kid] = public_key

    def clear_test_keys(self) -> None:
        """Clear test keys after testing."""
        self._test_signing_keys.clear()

    def get_signing_key(self, token: str) -> Any:
        """Retrieve signing key matching the token's kid header, supporting rotation."""
        try:
            unverified_header = jwt.get_unverified_header(token)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Malformed token header.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

        kid = unverified_header.get("kid")
        alg = unverified_header.get("alg")

        if not alg or alg not in self.algorithms:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Unsupported signing algorithm '{alg}'. Permitted: {self.algorithms}",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check registered test keys first
        if kid and kid in self._test_signing_keys:
            return self._test_signing_keys[kid]

        # Use PyJWKClient with automatic key rotation lookup
        if self._jwks_client is not None:
            try:
                signing_key = self._jwks_client.get_signing_key_from_jwt(token)
                return signing_key.key
            except PyJWKClientError as jwk_err:
                logger.warning(f"JWKS key lookup failed for kid '{kid}': {jwk_err}")
                # Re-initialize to handle potential key rotation
                self._initialize_jwks_client()
                if self._jwks_client:
                    try:
                        return self._jwks_client.get_signing_key_from_jwt(token).key
                    except Exception:
                        pass
            except Exception as exc:
                logger.error(f"Unexpected error retrieving JWKS key: {exc}")

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Unable to find cryptographic signing key for key ID '{kid}'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    def verify_token(self, token: str) -> Dict[str, Any]:
        """Cryptographically verify token signature, expiration, issuer, and audience."""
        signing_key = self.get_signing_key(token)

        try:
            payload = jwt.decode(
                token,
                key=signing_key,
                algorithms=self.algorithms,
                audience=self.audience,
                issuer=self.issuer,
                options={
                    "require": ["exp", "iss", "sub", "aud", "iat"],
                    "verify_exp": True,
                    "verify_iss": True,
                    "verify_aud": True,
                    "verify_iat": True,
                },
            )
            iat_val = payload.get("iat")
            exp_val = payload.get("exp")
            if iat_val is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token 'iat' (issued at) claim is missing.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            if exp_val is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token 'exp' (expiration) claim is missing.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # Ensure numeric types for temporal claims (protect against malformed non-numeric values)
            if not isinstance(iat_val, (int, float)) or isinstance(iat_val, bool):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token 'iat' (issued at) claim must be a numeric timestamp.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            if not isinstance(exp_val, (int, float)) or isinstance(exp_val, bool):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token 'exp' (expiration) claim must be a numeric timestamp.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            iat = int(iat_val)
            exp = int(exp_val)

            if exp <= iat:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token expiration ('exp') must be strictly later than issued-at ('iat') timestamp.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            if (exp - iat) > settings.MAX_JWT_LIFETIME_SECONDS:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Token lifetime ({exp - iat}s) exceeds maximum allowed duration ({settings.MAX_JWT_LIFETIME_SECONDS}s).",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return payload
        except jwt.ExpiredSignatureError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token has expired.",
                headers={"WWW-Authenticate": "Bearer error=\"invalid_token\", error_description=\"Token expired\""},
            ) from exc
        except jwt.ImmatureSignatureError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token 'iat' (issued at) is in the future beyond permitted clock tolerance.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        except jwt.MissingRequiredClaimError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token missing required claim: {str(exc)}",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        except jwt.InvalidIssuerError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token issuer. Expected '{self.issuer}'.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        except jwt.InvalidAudienceError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token audience. Expected '{self.audience}'.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        except jwt.InvalidSignatureError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token cryptographic signature.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        except (jwt.PyJWTError, ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token verification failed: {str(exc)}",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

    def extract_user_context(self, payload: Dict[str, Any]) -> AuthenticatedUser:
        """Extract user identity, role, and permissions strictly from trusted claims."""
        user_id = str(payload.get("sub", ""))
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token subject ('sub') claim is missing.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        email = payload.get("email")

        # SECURITY RULE: Never trust user_metadata for authorization.
        # Log a warning if a user attempted to put roles into user_metadata.
        user_meta = payload.get("user_metadata") or {}
        if "role" in user_meta or "roles" in user_meta:
            logger.warning(
                f"Ignored unauthorized role definition in client-editable user_metadata for user {user_id}"
            )

        # Extract role strictly from server-controlled app_metadata
        app_meta = payload.get("app_metadata") or {}
        raw_role = app_meta.get("role")
        if not raw_role and isinstance(app_meta.get("roles"), list) and app_meta["roles"]:
            raw_role = app_meta["roles"][0]

        role: Optional[UserRole] = None
        if raw_role:
            try:
                role = UserRole(str(raw_role).lower())
            except ValueError:
                logger.warning(f"Unrecognized application role '{raw_role}' for user {user_id}")
                role = None

        # Extract patient-level permissions strictly from app_metadata
        patient_ids: List[str] = []
        raw_patients = app_meta.get("patient_ids") or app_meta.get("assigned_patients") or []
        if isinstance(raw_patients, list):
            patient_ids = [str(pid) for pid in raw_patients]

        return AuthenticatedUser(
            id=user_id,
            email=email,
            role=role,
            patient_ids=patient_ids,
            app_metadata=app_meta,
        )


# Global verifier instance
jwt_verifier = SupabaseJWTVerifier()

# Register local development ES256 key for testing and interactive local usage
_DEV_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
_DEV_PUBLIC_KEY = _DEV_PRIVATE_KEY.public_key()
_DEV_KID = "dev-ec-kid-01"
jwt_verifier.register_test_key(_DEV_KID, _DEV_PUBLIC_KEY)


def create_dev_token(
    sub: str = "550e8400-e29b-41d4-a716-446655440001",
    email: str = "dr.smith@exacerbalert.org",
    role: UserRole = UserRole.CLINICIAN,
    patient_ids: Optional[List[str]] = None,
    expires_in_seconds: int = 3600,
) -> str:
    """Generate a cryptographically valid ES256 Supabase JWT for local dev/testing."""
    now = int(time.time())
    resolved_patients = (
        patient_ids
        if patient_ids is not None
        else ([str(i) for i in range(1, 100)] if role == UserRole.CLINICIAN else [])
    )
    payload = {
        "sub": sub,
        "email": email,
        "aud": settings.SUPABASE_JWT_AUDIENCE,
        "iss": settings.effective_jwt_issuer,
        "iat": now,
        "exp": now + expires_in_seconds,
        "app_metadata": {
            "provider": "email",
            "role": role.value,
            "roles": [role.value],
            "patient_ids": resolved_patients,
        },
        "user_metadata": {},
    }
    return jwt.encode(payload, _DEV_PRIVATE_KEY, algorithm="ES256", headers={"kid": _DEV_KID})


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(oauth2_bearer),
) -> AuthenticatedUser:
    """FastAPI dependency: Extract and cryptographically verify Supabase Bearer token."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Missing Bearer token in Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = jwt_verifier.verify_token(credentials.credentials)
    return jwt_verifier.extract_user_context(payload)


def require_role(allowed_roles: Union[UserRole, List[UserRole]]):
    """Dependency factory enforcing role-based access control (RBAC)."""
    if isinstance(allowed_roles, UserRole):
        roles_set = {allowed_roles}
    else:
        roles_set = set(allowed_roles)

    async def role_dependency(
        current_user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        if not current_user.role or current_user.role not in roles_set:
            allowed_names = [r.value for r in roles_set]
            current_name = current_user.role.value if current_user.role else "unassigned"
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "FORBIDDEN_ROLE",
                    "message": f"Access denied. Required role in {allowed_names}, active role is '{current_name}'.",
                },
            )
        return current_user

    return role_dependency


def get_authoritative_user_status(user_id: str, db: Any) -> Optional[Dict[str, Any]]:
    """Query authoritative user status from database (via get_auth_user_status or auth.users)."""
    from sqlalchemy import text

    # 1. Try PostgreSQL function public.get_auth_user_status(CAST(:uid AS uuid))
    try:
        query = text("""
            SELECT id, email, role, permissions, banned_until, deleted_at
            FROM public.get_auth_user_status(CAST(:uid AS uuid))
        """)
        row = db.execute(query, {"uid": user_id}).fetchone()
        if row:
            return {
                "id": str(row.id),
                "email": row.email,
                "role": row.role,
                "permissions": row.permissions or [],
                "banned_until": row.banned_until,
                "deleted_at": row.deleted_at,
            }
        # If executed successfully on PostgreSQL and returned 0 rows, user does not exist
        try:
            dialect_name = db.get_bind().dialect.name
            if dialect_name != "sqlite":
                return None
        except Exception:
            pass
    except Exception as exc:
        logger.debug(f"public.get_auth_user_status execution note: {exc}")

    # 2. SQLite test fixture fallback (works in test SQLite with attached auth schema)
    try:
        import json
        query = text("SELECT id, email, raw_app_meta_data, banned_until, deleted_at FROM auth.users WHERE id = :uid")
        row = db.execute(query, {"uid": user_id}).fetchone()
        if row:
            meta = row.raw_app_meta_data or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            return {
                "id": str(row.id),
                "email": row.email,
                "role": meta.get("role"),
                "permissions": meta.get("permissions", []),
                "banned_until": getattr(row, "banned_until", None),
                "deleted_at": getattr(row, "deleted_at", None),
            }
    except Exception as exc:
        logger.debug(f"Could not query authoritative status for user {user_id}: {exc}")
        return None

    return None


def require_authoritative_user(allowed_roles: Union[UserRole, List[UserRole]]):
    """Dependency factory enforcing real-time authoritative account status verification for sensitive routes.

    Validates:
    1. Cryptographically valid JWT token and matching role.
    2. Re-verifies active account status in database (banned_until, deleted_at).
    3. Re-verifies that current database role matches the required role (detects immediate demotion).
    """
    if isinstance(allowed_roles, UserRole):
        roles_set = {allowed_roles}
    else:
        roles_set = set(allowed_roles)

    async def authoritative_dependency(
        current_user: AuthenticatedUser = Depends(get_current_user),
        db: Optional[Session] = Depends(get_db),
    ) -> AuthenticatedUser:
        # Base check from token
        if not current_user.role or current_user.role not in roles_set:
            allowed_names = [r.value for r in roles_set]
            current_name = current_user.role.value if current_user.role else "unassigned"
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "FORBIDDEN_ROLE",
                    "message": f"Access denied. Required role in {allowed_names}, active role is '{current_name}'.",
                },
            )

        # Authoritative database check for sensitive operations
        if db is not None:
            user_status = get_authoritative_user_status(current_user.id, db)
            if user_status is not None:
                # Check deleted
                if user_status.get("deleted_at") is not None:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail={"code": "ACCOUNT_DELETED", "message": "User account has been deleted."},
                    )
                # Check banned
                banned_until = user_status.get("banned_until")
                if banned_until is not None:
                    from datetime import datetime, timezone
                    now = datetime.now(timezone.utc)
                    if isinstance(banned_until, str):
                        try:
                            banned_until = datetime.fromisoformat(banned_until.replace("Z", "+00:00"))
                        except Exception:
                            try:
                                banned_until = datetime.strptime(banned_until.split(".")[0], "%Y-%m-%d %H:%M:%S")
                            except Exception:
                                pass
                    if hasattr(banned_until, "tzinfo"):
                        if banned_until.tzinfo is None:
                            banned_until = banned_until.replace(tzinfo=timezone.utc)
                        if banned_until > now:
                            raise HTTPException(
                                status_code=status.HTTP_403_FORBIDDEN,
                                detail={"code": "ACCOUNT_BANNED", "message": "User account is suspended."},
                            )
                # Check authoritative role (detect demotion)
                db_role_str = user_status.get("role")
                if db_role_str:
                    try:
                        db_role = UserRole(db_role_str.lower())
                        if db_role not in roles_set:
                            allowed_names = [r.value for r in roles_set]
                            raise HTTPException(
                                status_code=status.HTTP_403_FORBIDDEN,
                                detail={
                                    "code": "ROLE_DEMOTED",
                                    "message": f"Access denied. Authoritative user role is '{db_role.value}', which is not in {allowed_names}.",
                                },
                            )
                        current_user.role = db_role
                    except ValueError:
                        pass

        return current_user

    return authoritative_dependency


def has_active_patient_assignment(user_id: str, patient_id: Union[str, int], db: Any) -> bool:
    """Verify whether clinician/user has an active (unrevoked) assignment to patient in database."""
    from sqlalchemy import text
    try:
        pid = int(patient_id)
    except (ValueError, TypeError):
        return False

    dialect_name = getattr(getattr(db, "bind", None), "dialect", None)
    if dialect_name is None:
        try:
            dialect_name = db.get_bind().dialect.name
        except Exception:
            dialect_name = "postgresql"
    else:
        dialect_name = dialect_name.name

    if dialect_name == "postgresql":
        query = text("""
            SELECT 1 FROM public.clinician_patient_assignments
            WHERE clinician_id = CAST(:cid AS uuid)
              AND patient_id = :pid
              AND revoked_at IS NULL
            LIMIT 1
        """)
        try:
            row = db.execute(query, {"cid": user_id, "pid": pid}).fetchone()
            return row is not None
        except Exception as exc:
            logger.debug(f"PostgreSQL active assignment check note: {exc}")
            try:
                query_alt = text("""
                    SELECT 1 FROM clinician_patient_assignments
                    WHERE clinician_id = CAST(:cid AS uuid)
                      AND patient_id = :pid
                      AND revoked_at IS NULL
                    LIMIT 1
                """)
                row = db.execute(query_alt, {"cid": user_id, "pid": pid}).fetchone()
                return row is not None
            except Exception:
                return False
    else:
        query = text("""
            SELECT 1 FROM clinician_patient_assignments
            WHERE clinician_id = :cid
              AND patient_id = :pid
              AND revoked_at IS NULL
            LIMIT 1
        """)
        try:
            row = db.execute(query, {"cid": user_id, "pid": pid}).fetchone()
            return row is not None
        except Exception as exc:
            logger.debug(f"Active assignment check note: {exc}")
            return False


def get_active_patient_assignments(user_id: str, db: Any) -> List[int]:
    """Retrieve list of numeric patient IDs actively assigned to clinician/user in database."""
    from sqlalchemy import text

    dialect_name = getattr(getattr(db, "bind", None), "dialect", None)
    if dialect_name is None:
        try:
            dialect_name = db.get_bind().dialect.name
        except Exception:
            dialect_name = "postgresql"
    else:
        dialect_name = dialect_name.name

    if dialect_name == "postgresql":
        query = text("""
            SELECT patient_id FROM public.clinician_patient_assignments
            WHERE clinician_id = CAST(:cid AS uuid)
              AND revoked_at IS NULL
            ORDER BY patient_id ASC
        """)
        try:
            rows = db.execute(query, {"cid": user_id}).fetchall()
            return [int(r[0]) for r in rows]
        except Exception as exc:
            logger.debug(f"PostgreSQL active assignments query note: {exc}")
            try:
                query_alt = text("""
                    SELECT patient_id FROM clinician_patient_assignments
                    WHERE clinician_id = CAST(:cid AS uuid)
                      AND revoked_at IS NULL
                    ORDER BY patient_id ASC
                """)
                rows = db.execute(query_alt, {"cid": user_id}).fetchall()
                return [int(r[0]) for r in rows]
            except Exception:
                return []
    else:
        query = text("""
            SELECT patient_id FROM clinician_patient_assignments
            WHERE clinician_id = :cid
              AND revoked_at IS NULL
            ORDER BY patient_id ASC
        """)
        try:
            rows = db.execute(query, {"cid": user_id}).fetchall()
            return [int(r[0]) for r in rows]
        except Exception as exc:
            logger.debug(f"Active assignments query note: {exc}")
            return []


def verify_patient_access(
    patient_id: Union[str, int],
    user: AuthenticatedUser,
    db: Optional[Any] = None,
) -> None:
    """Enforce patient-level authorization and least privilege.

    Authoritative enforcement rules:
    - Clinicians: When db is provided, verifies active assignment directly against
      clinician_patient_assignments (WHERE revoked_at IS NULL).
      Denies access immediately (HTTP 403 FORBIDDEN_PATIENT_ACCESS) if assignment is missing or revoked.
      When db is None, falls back to token claims (user.can_access_patient).
    - Administrators: Least privilege enforced. Clinical data access is NOT granted
      automatically. If db is provided, requires active assignment in clinician_patient_assignments.
      If unauthorized, raises HTTP 403 FORBIDDEN_CLINICAL_ACCESS.
      When db is None, falls back to token claims.
    - Other/unassigned roles: Denied with HTTP 403 FORBIDDEN_UNASSIGNED_ROLE.
    """
    if user.role == UserRole.CLINICIAN:
        if db is not None:
            if not has_active_patient_assignment(user.id, patient_id, db):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "code": "FORBIDDEN_PATIENT_ACCESS",
                        "message": f"Access denied. Clinician is not authorized to access records for patient {patient_id}.",
                    },
                )
        else:
            if not user.can_access_patient(patient_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "code": "FORBIDDEN_PATIENT_ACCESS",
                        "message": f"Access denied. Clinician is not authorized to access records for patient {patient_id}.",
                    },
                )
    elif user.role == UserRole.ADMINISTRATOR:
        if db is not None:
            if not has_active_patient_assignment(user.id, patient_id, db):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "code": "FORBIDDEN_CLINICAL_ACCESS",
                        "message": "Access denied. Administrator role does not grant clinical data access without explicit patient assignment.",
                    },
                )
        else:
            if not user.can_access_patient(patient_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "code": "FORBIDDEN_CLINICAL_ACCESS",
                        "message": "Access denied. Administrator role does not grant clinical data access without explicit patient assignment.",
                    },
                )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "FORBIDDEN_UNASSIGNED_ROLE",
                "message": "Access denied. User has no assigned role.",
            },
        )
