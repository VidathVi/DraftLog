"""Tenancy dependency and permission matrix — resolves a JWT to (user, membership, org).

Every app-surface route that needs org context depends on ``CurrentAuth``.
It enforces:
  - Deactivated users are rejected (``is_active=False``).
  - Suspended orgs are rejected (``suspended_at IS NOT NULL``).
  - Cross-org access returns 404, never 403 (don't leak existence).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import APIException, ResourceNotFoundException
from app.models import Membership, Organization, User

if TYPE_CHECKING:
    from app.models import Plan, Team


@dataclass(frozen=True, slots=True)
class AuthContext:
    """Resolved auth state for an app-surface request."""

    user: User
    membership: Membership
    org: Organization


async def resolve_auth_context(
    session: AsyncSession,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> AuthContext:
    """Load and validate the full (user, membership, org) triple.

    Raises 404 for any missing or invalid combination so cross-org probes
    cannot distinguish "wrong org" from "does not exist".
    """
    # 1. Load user — reject if not found or deactivated
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if user is None or not user.is_active:
        raise ResourceNotFoundException("Not found")

    # 2. Load org — reject if not found or suspended
    result = await session.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = result.scalars().first()
    if org is None or org.suspended_at is not None:
        raise ResourceNotFoundException("Not found")

    # 3. Load membership — reject if user has no membership in this org
    result = await session.execute(
        select(Membership).where(
            Membership.org_id == org_id,
            Membership.user_id == user_id,
        )
    )
    membership = result.scalars().first()
    if membership is None:
        raise ResourceNotFoundException("Not found")

    return AuthContext(user=user, membership=membership, org=org)


# ---------------------------------------------------------------------------
# Canonical Role Names & Permission Matrix Helpers
# ---------------------------------------------------------------------------

ROLE_OWNER = "owner"
ROLE_ADMIN = "admin"
ROLE_MEMBER = "member"

VALID_ROLES = {ROLE_OWNER, ROLE_ADMIN, ROLE_MEMBER}
_ADMIN_ROLES = {ROLE_OWNER, ROLE_ADMIN}


def require_org_admin(ctx: AuthContext) -> None:
    """Raise 403 if the caller is not an org owner or admin."""
    if ctx.membership.org_role not in _ADMIN_ROLES:
        raise APIException(
            status_code=403,
            code="INSUFFICIENT_ROLE",
            message="This action requires an admin or owner role.",
        )


def require_org_owner(ctx: AuthContext) -> None:
    """Raise 403 if the caller is not an org owner."""
    if ctx.membership.org_role != ROLE_OWNER:
        raise APIException(
            status_code=403,
            code="INSUFFICIENT_ROLE",
            message="This action requires the owner role.",
        )


def check_can_change_role(
    actor_ctx: AuthContext,
    target_membership: Membership,
    new_role: str,
    owner_count: int,
) -> None:
    """Enforce role change permissions per Phase 2 matrix.

    - Owner can change any role (except demoting the last owner).
    - Admin can change roles, but NOT for owners, NOT their own role, and cannot promote to owner.
    - Member cannot change any roles.
    - Demoting or removing the last owner is always prohibited.
    """
    if new_role not in VALID_ROLES:
        raise APIException(
            status_code=400,
            code="INVALID_ROLE",
            message=f"Invalid role '{new_role}'. Must be one of: {', '.join(sorted(VALID_ROLES))}",
        )

    # Protection: Never demote the last owner
    if (
        target_membership.org_role == ROLE_OWNER
        and new_role != ROLE_OWNER
        and owner_count <= 1
    ):
        raise APIException(
            status_code=400,
            code="LAST_OWNER",
            message="Cannot remove or demote the last owner of an organization.",
        )

    actor_role = actor_ctx.membership.org_role

    if actor_role == ROLE_OWNER:
        return

    if actor_role == ROLE_ADMIN:
        # Admin cannot change an owner's role
        if target_membership.org_role == ROLE_OWNER:
            raise APIException(
                status_code=403,
                code="INSUFFICIENT_ROLE",
                message="Admins cannot modify an owner's role.",
            )
        # Admin cannot change their own role
        if actor_ctx.membership.id == target_membership.id:
            raise APIException(
                status_code=403,
                code="CANNOT_MODIFY_SELF",
                message="Admins cannot change their own role.",
            )
        # Admin cannot promote someone to owner
        if new_role == ROLE_OWNER:
            raise APIException(
                status_code=403,
                code="INSUFFICIENT_ROLE",
                message="Only owners can promote members to owner.",
            )
        return

    raise APIException(
        status_code=403,
        code="INSUFFICIENT_ROLE",
        message="Only owners and admins can change member roles.",
    )


def check_can_remove_member(
    actor_ctx: AuthContext,
    target_membership: Membership,
    owner_count: int,
) -> None:
    """Enforce member removal permissions."""
    if target_membership.org_role == ROLE_OWNER:
        if owner_count <= 1:
            raise APIException(
                status_code=400,
                code="LAST_OWNER",
                message="Cannot remove the last owner of an organization.",
            )
        if actor_ctx.membership.org_role != ROLE_OWNER:
            raise APIException(
                status_code=403,
                code="INSUFFICIENT_ROLE",
                message="Only owners can remove another owner.",
            )

    actor_role = actor_ctx.membership.org_role

    if actor_role == ROLE_OWNER:
        return

    if actor_role == ROLE_ADMIN:
        if actor_ctx.membership.id == target_membership.id:
            raise APIException(
                status_code=403,
                code="CANNOT_MODIFY_SELF",
                message="Admins cannot remove themselves via this endpoint.",
            )
        return

    raise APIException(
        status_code=403,
        code="INSUFFICIENT_ROLE",
        message="Only owners and admins can remove members.",
    )


def require_view_team_week(actor_ctx: AuthContext, team: Team) -> None:
    """Enforce team week visibility per Phase 2 matrix.

    Owner: ✔
    Admin: ✔
    Member: ✗
    Team lead: ✔ (own team)
    """
    if actor_ctx.membership.org_role in _ADMIN_ROLES:
        return

    if team.lead_membership_id == actor_ctx.membership.id:
        return

    raise APIException(
        status_code=403,
        code="INSUFFICIENT_ROLE",
        message="Only org admins and the team lead can view the team's week.",
    )


def require_approve_plan(
    actor_ctx: AuthContext,
    plan: Plan,
    team: Team,
) -> None:
    """Enforce plan approval and send-back permissions per Phase 2 matrix.

    - If the plan belongs to the team lead themselves, an org owner or admin must approve.
    - Otherwise, only the team lead of that plan's team can approve or send back.
    """
    is_leads_own_plan = (plan.membership_id == team.lead_membership_id)

    if is_leads_own_plan:
        if actor_ctx.membership.org_role not in _ADMIN_ROLES:
            raise APIException(
                status_code=403,
                code="INSUFFICIENT_ROLE",
                message="A team lead's plan must be approved by an org owner or admin.",
            )
        return

    # Regular member plan: must be the lead of the team
    if team.lead_membership_id != actor_ctx.membership.id:
        raise APIException(
            status_code=403,
            code="INSUFFICIENT_ROLE",
            message="Only the team lead can approve or send back this plan.",
        )
