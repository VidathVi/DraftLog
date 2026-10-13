"""Unit tests for Phase 2 tenancy and permission matrix helpers."""

import uuid

import pytest

from app.exceptions import APIException
from app.models import Membership, Organization, Plan, Team, User
from app.tenancy import (
    ROLE_ADMIN,
    ROLE_MEMBER,
    ROLE_OWNER,
    AuthContext,
    check_can_change_role,
    check_can_remove_member,
    require_approve_plan,
    require_org_admin,
    require_org_owner,
    require_view_team_week,
)


def _make_auth_ctx(role: str) -> AuthContext:
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    membership_id = uuid.uuid4()

    user = User(
        id=user_id,
        first_name="Test",
        last_name="User",
        email=f"user-{user_id}@example.com",
        is_active=True,
    )
    org = Organization(id=org_id, name="Test Org", slug=f"org-{org_id}")
    membership = Membership(
        id=membership_id,
        org_id=org_id,
        user_id=user_id,
        org_role=role,
    )
    return AuthContext(user=user, membership=membership, org=org)


def test_require_org_admin():
    owner_ctx = _make_auth_ctx(ROLE_OWNER)
    admin_ctx = _make_auth_ctx(ROLE_ADMIN)
    member_ctx = _make_auth_ctx(ROLE_MEMBER)

    require_org_admin(owner_ctx)
    require_org_admin(admin_ctx)

    with pytest.raises(APIException) as exc_info:
        require_org_admin(member_ctx)
    assert exc_info.value.status_code == 403


def test_require_org_owner():
    owner_ctx = _make_auth_ctx(ROLE_OWNER)
    admin_ctx = _make_auth_ctx(ROLE_ADMIN)
    member_ctx = _make_auth_ctx(ROLE_MEMBER)

    require_org_owner(owner_ctx)

    with pytest.raises(APIException) as exc_info:
        require_org_owner(admin_ctx)
    assert exc_info.value.status_code == 403

    with pytest.raises(APIException) as exc_info:
        require_org_owner(member_ctx)
    assert exc_info.value.status_code == 403


def test_cannot_demote_or_remove_last_owner():
    owner_ctx = _make_auth_ctx(ROLE_OWNER)
    target_owner = Membership(
        id=uuid.uuid4(),
        org_id=owner_ctx.org.id,
        user_id=uuid.uuid4(),
        org_role=ROLE_OWNER,
    )

    # Demoting last owner fails with 400 LAST_OWNER
    with pytest.raises(APIException) as exc_info:
        check_can_change_role(owner_ctx, target_owner, ROLE_ADMIN, owner_count=1)
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "LAST_OWNER"

    # Removing last owner fails with 400 LAST_OWNER
    with pytest.raises(APIException) as exc_info:
        check_can_remove_member(owner_ctx, target_owner, owner_count=1)
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "LAST_OWNER"

    # Demoting owner when there are 2 owners succeeds
    check_can_change_role(owner_ctx, target_owner, ROLE_ADMIN, owner_count=2)
    # Removing owner when there are 2 owners succeeds
    check_can_remove_member(owner_ctx, target_owner, owner_count=2)


def test_admin_role_change_restrictions():
    admin_ctx = _make_auth_ctx(ROLE_ADMIN)
    target_owner = Membership(
        id=uuid.uuid4(),
        org_id=admin_ctx.org.id,
        user_id=uuid.uuid4(),
        org_role=ROLE_OWNER,
    )
    target_member = Membership(
        id=uuid.uuid4(),
        org_id=admin_ctx.org.id,
        user_id=uuid.uuid4(),
        org_role=ROLE_MEMBER,
    )

    # Admin cannot modify an owner's role
    with pytest.raises(APIException) as exc_info:
        check_can_change_role(admin_ctx, target_owner, ROLE_MEMBER, owner_count=2)
    assert exc_info.value.status_code == 403

    # Admin cannot modify their own role
    with pytest.raises(APIException) as exc_info:
        check_can_change_role(admin_ctx, admin_ctx.membership, ROLE_MEMBER, owner_count=1)
    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "CANNOT_MODIFY_SELF"

    # Admin cannot promote anyone to owner
    with pytest.raises(APIException) as exc_info:
        check_can_change_role(admin_ctx, target_member, ROLE_OWNER, owner_count=1)
    assert exc_info.value.status_code == 403

    # Admin CAN promote member to admin
    check_can_change_role(admin_ctx, target_member, ROLE_ADMIN, owner_count=1)


def test_view_team_week_permissions():
    owner_ctx = _make_auth_ctx(ROLE_OWNER)
    admin_ctx = _make_auth_ctx(ROLE_ADMIN)
    lead_ctx = _make_auth_ctx(ROLE_MEMBER)
    other_member_ctx = _make_auth_ctx(ROLE_MEMBER)

    team = Team(
        id=uuid.uuid4(),
        org_id=owner_ctx.org.id,
        name="Backend Team",
        lead_membership_id=lead_ctx.membership.id,
    )

    # Owner and admin can view any team week
    require_view_team_week(owner_ctx, team)
    require_view_team_week(admin_ctx, team)

    # Lead can view their own team week
    require_view_team_week(lead_ctx, team)

    # Other member cannot view team week
    with pytest.raises(APIException) as exc_info:
        require_view_team_week(other_member_ctx, team)
    assert exc_info.value.status_code == 403


def test_approve_plan_permissions():
    owner_ctx = _make_auth_ctx(ROLE_OWNER)
    admin_ctx = _make_auth_ctx(ROLE_ADMIN)
    lead_ctx = _make_auth_ctx(ROLE_MEMBER)
    other_lead_ctx = _make_auth_ctx(ROLE_MEMBER)
    member_ctx = _make_auth_ctx(ROLE_MEMBER)

    team = Team(
        id=uuid.uuid4(),
        org_id=owner_ctx.org.id,
        name="Backend Team",
        lead_membership_id=lead_ctx.membership.id,
    )

    member_plan = Plan(
        id=uuid.uuid4(),
        org_id=owner_ctx.org.id,
        membership_id=member_ctx.membership.id,
        team_id=team.id,
    )

    lead_plan = Plan(
        id=uuid.uuid4(),
        org_id=owner_ctx.org.id,
        membership_id=lead_ctx.membership.id,
        team_id=team.id,
    )

    # 1. Regular member's plan:
    # Team lead can approve
    require_approve_plan(lead_ctx, member_plan, team)

    # Other lead cannot approve
    with pytest.raises(APIException) as exc_info:
        require_approve_plan(other_lead_ctx, member_plan, team)
    assert exc_info.value.status_code == 403

    # Member cannot approve
    with pytest.raises(APIException) as exc_info:
        require_approve_plan(member_ctx, member_plan, team)
    assert exc_info.value.status_code == 403

    # 2. Lead's own plan:
    # Must be approved by org owner or admin
    require_approve_plan(owner_ctx, lead_plan, team)
    require_approve_plan(admin_ctx, lead_plan, team)

    # Lead cannot approve their own plan
    with pytest.raises(APIException) as exc_info:
        require_approve_plan(lead_ctx, lead_plan, team)
    assert exc_info.value.status_code == 403
