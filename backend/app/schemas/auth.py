"""Pydantic schemas for authentication and role-based access control (RBAC)."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class UserRole(str, Enum):
    """Approved application roles for ExacerbAlert."""

    CLINICIAN = "clinician"
    ADMINISTRATOR = "administrator"


class AuthenticatedUser(BaseModel):
    """Authenticated user context extracted from verified JWT claims."""

    id: str = Field(..., description="Unique user identifier (Supabase auth.users UUID)")
    email: Optional[str] = Field(default=None, description="User email address")
    role: Optional[UserRole] = Field(default=None, description="Assigned role from server-controlled app_metadata")
    patient_ids: List[str] = Field(
        default_factory=list,
        description="List of authorized patient IDs assigned to this clinician",
    )
    app_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Server-controlled app_metadata from Supabase Auth",
    )

    def can_access_patient(self, patient_id: Union[str, int]) -> bool:
        """Evaluate if user is authorized to access records for a given patient.

        Rules:
        - Clinicians: Authorized strictly if patient_id is present in patient_ids.
        - Administrators: Least privilege enforced. Clinical access requires explicit
          clinical patient assignment or permission in app_metadata.
        - Unassigned/empty: Denied by default.
        """
        pid_str = str(patient_id)
        authorized_set = {str(p) for p in self.patient_ids}
        return pid_str in authorized_set


class UserResponse(BaseModel):
    """Public user response for admin management views."""

    id: str
    email: Optional[str] = None
    role: Optional[UserRole] = None
    patient_ids: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class RoleAssignmentRequest(BaseModel):
    """Request payload for an administrator assigning a role."""

    role: UserRole = Field(..., description="Role to assign to the target user")


class PatientAccessAssignmentRequest(BaseModel):
    """Request payload for an administrator assigning patient permissions."""

    patient_ids: List[str] = Field(
        ...,
        description="List of patient IDs the clinician is permitted to access",
    )


class AuthMeResponse(BaseModel):
    """User profile and active permissions response for /auth/me."""

    id: str
    email: Optional[str] = None
    role: Optional[UserRole] = None
    patient_ids: List[str] = Field(default_factory=list)
    permissions: List[str] = Field(
        default_factory=list,
        description="Computed permission capabilities for the active session",
    )
