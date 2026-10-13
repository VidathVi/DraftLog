from __future__ import annotations

from pydantic import UUID4, EmailStr, Field

from app.schemas import DateTime, Model

# ---------------------------------------------------------------------------
# Auth & User Schemas
# ---------------------------------------------------------------------------


class AuthRequest(Model):
    email: EmailStr
    password: str
    org_id: UUID4 | None = None


class SignUpRequest(Model):
    first_name: str
    last_name: str
    email: EmailStr
    password: str
    org_name: str | None = None
    invite_token: str | None = None


class UserResponse(Model):
    id: UUID4
    created_at: DateTime
    updated_at: DateTime | None = None
    first_name: str
    last_name: str
    email: str


class AuthResponse(Model):
    access_token: str
    user: UserResponse
    org: OrganizationResponse | None = None
    membership: MembershipResponse | None = None


# ---------------------------------------------------------------------------
# Organization & Membership Schemas
# ---------------------------------------------------------------------------


class OrganizationResponse(Model):
    id: UUID4
    created_at: DateTime
    updated_at: DateTime | None = None
    name: str
    slug: str


class OrganizationUpdateRequest(Model):
    name: str | None = None
    slug: str | None = None


class MembershipResponse(Model):
    id: UUID4
    created_at: DateTime
    org_id: UUID4
    user_id: UUID4
    org_role: str


class MemberWithUserResponse(Model):
    id: UUID4
    created_at: DateTime
    org_role: str
    user: UserResponse


class UpdateMemberRoleRequest(Model):
    org_role: str


# ---------------------------------------------------------------------------
# Invite Schemas
# ---------------------------------------------------------------------------


class InviteCreateRequest(Model):
    org_role: str = "member"
    expires_in_days: int = 7


class InviteResponse(Model):
    id: UUID4
    created_at: DateTime
    org_id: UUID4
    org_role: str
    expires_at: DateTime
    raw_token: str | None = None
    created_by: MemberWithUserResponse | None = None


class InvitePublicResponse(Model):
    org_name: str
    org_slug: str
    org_role: str
    inviter_name: str | None = None
    expires_at: DateTime


# ---------------------------------------------------------------------------
# Team Schemas
# ---------------------------------------------------------------------------


class TeamMemberItem(Model):
    membership_id: UUID4
    user: UserResponse
    org_role: str


class TeamResponse(Model):
    id: UUID4
    created_at: DateTime
    org_id: UUID4
    name: str
    lead_membership_id: UUID4 | None = None
    lead: MemberWithUserResponse | None = None
    member_count: int = 0


class TeamDetailResponse(Model):
    id: UUID4
    created_at: DateTime
    org_id: UUID4
    name: str
    lead_membership_id: UUID4 | None = None
    lead: MemberWithUserResponse | None = None
    members: list[TeamMemberItem] = Field(default_factory=list)


class TeamCreateRequest(Model):
    name: str
    lead_membership_id: UUID4 | None = None


class TeamUpdateRequest(Model):
    name: str | None = None
    lead_membership_id: UUID4 | None = None
    clear_lead: bool = False


class AddTeamMemberRequest(Model):
    membership_id: UUID4
