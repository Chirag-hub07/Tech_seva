"""Authentication endpoints for current session inspection and development tokens."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.app.config import settings
from backend.app.core.auth import create_dev_token, get_current_user
from backend.app.schemas.auth import AuthenticatedUser, AuthMeResponse, UserRole

router = APIRouter(prefix="/auth", tags=["Authentication"])


class TokenRequest(BaseModel):
    """Token request schema for session initialization."""

    email: Optional[str] = Field(default=None, description="User email address")
    password: Optional[str] = Field(default=None, description="Password or access token")
    role: Optional[UserRole] = Field(default=UserRole.CLINICIAN, description="Requested role (development/test)")


class TokenResponse(BaseModel):
    """Bearer token response schema."""

    access_token: str
    token_type: str = "bearer"
    user: AuthMeResponse


def compute_permissions(user: AuthenticatedUser) -> List[str]:
    """Compute active permissions based on role and explicit patient access."""
    perms = []
    if user.role == UserRole.CLINICIAN:
        perms.extend([
            "clinical:read_patients",
            "clinical:read_measurements",
            "clinical:read_predictions",
            "clinical:read_alerts",
            "clinical:acknowledge_alerts",
        ])
    elif user.role == UserRole.ADMINISTRATOR:
        perms.extend([
            "admin:manage_users",
            "admin:assign_roles",
            "admin:manage_patient_access",
            "admin:manage_settings",
        ])
        # Administrators only get clinical permissions if explicitly assigned
        if user.patient_ids:
            perms.extend([
                "clinical:read_patients",
                "clinical:read_measurements",
                "clinical:read_predictions",
                "clinical:read_alerts",
            ])
    return perms


@router.post(
    "/token",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Issue or exchange authentication token",
    description="Issues an asymmetric ES256 Supabase JWT for authenticated session initialization.",
)
def issue_token(payload: TokenRequest) -> TokenResponse:
    """Issue session token with cryptographic ES256 signature."""
    # Token issuance is restricted strictly to local development and automated testing
    if settings.ENVIRONMENT not in ("development", "testing"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Direct token issuance endpoint is disabled in non-development environments.",
        )

    # In development/testing, issue signed ES256 token matching the requested role
    role = payload.role or (UserRole.ADMINISTRATOR if "admin" in (payload.email or "").lower() else UserRole.CLINICIAN)
    email = payload.email or ("admin@exacerbalert.org" if role == UserRole.ADMINISTRATOR else "dr.smith@exacerbalert.org")
    sub = "550e8400-e29b-41d4-a716-446655440002" if role == UserRole.ADMINISTRATOR else "550e8400-e29b-41d4-a716-446655440001"
    patient_ids = [str(i) for i in range(1, 100)] if role == UserRole.CLINICIAN else []

    token = create_dev_token(
        sub=sub,
        email=email,
        role=role,
        patient_ids=patient_ids,
    )

    user_ctx = AuthenticatedUser(
        id=sub,
        email=email,
        role=role,
        patient_ids=patient_ids,
        app_metadata={"role": role.value, "patient_ids": patient_ids},
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=AuthMeResponse(
            id=sub,
            email=email,
            role=role,
            patient_ids=patient_ids,
            permissions=compute_permissions(user_ctx),
        ),
    )


@router.get(
    "/me",
    response_model=AuthMeResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated user",
    description="Returns verified user identity, role, assigned patients, and calculated permissions.",
)
def get_me(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> AuthMeResponse:
    """Return active authenticated user context."""
    return AuthMeResponse(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        patient_ids=current_user.patient_ids,
        permissions=compute_permissions(current_user),
    )
