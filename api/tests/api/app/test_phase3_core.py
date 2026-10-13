import uuid

import pytest
from faker import Faker

from app.models import Membership, Organization, User
from app.security import JWT_AUDIENCE_APP, generate_jwt_token, hash_password

fake = Faker()


async def _create_user(session, *, email=None, is_active=True, password="password123"):
    user = User(
        first_name=fake.first_name(),
        last_name=fake.last_name(),
        email=email or fake.email().lower(),
        password=hash_password(password),
        is_active=is_active,
    )
    session.add(user)
    await session.flush()
    return user


async def _create_org_with_owner(session, *, user=None):
    if user is None:
        user = await _create_user(session)
    org = Organization(
        name=fake.company(),
        slug=f"org-{uuid.uuid4().hex[:8]}",
    )
    session.add(org)
    await session.flush()

    membership = Membership(
        org_id=org.id,
        user_id=user.id,
        org_role="owner",
    )
    session.add(membership)
    await session.flush()
    return org, user, membership


def _auth_cookie(user_id: uuid.UUID, org_id: uuid.UUID | None = None) -> str:
    token = generate_jwt_token(
        {"sub": str(user_id)},
        audience=JWT_AUDIENCE_APP,
        org_id=str(org_id) if org_id else None,
    )
    return f"Bearer {token}"


# ---------------------------------------------------------------------------
# Sign-up Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_signup_with_new_org(async_client):
    email = fake.email().lower()
    res = await async_client.post(
        "/app/auth/sign-up",
        json={
            "first_name": "Alice",
            "last_name": "Smith",
            "email": email,
            "password": "SecurePassword1!",
            "org_name": "Acme Corp",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert "access_token" in data
    assert data["user"]["email"] == email
    assert data["org"]["name"] == "Acme Corp"
    assert data["membership"]["org_role"] == "owner"


@pytest.mark.asyncio
async def test_signup_and_join_via_invite(async_client, session_factory):
    # 1. Create org and invite
    async with session_factory() as session:
        org, owner, _ = await _create_org_with_owner(session)
        await session.commit()

    # Create invite as owner
    async_client.cookies.set("access_token", _auth_cookie(owner.id, org.id))
    invite_res = await async_client.post(
        "/app/org/invites",
        json={"org_role": "member", "expires_in_days": 5},
    )
    assert invite_res.status_code == 201
    raw_token = invite_res.json()["raw_token"]

    # 2. Public preview
    async_client.cookies.clear()
    preview_res = await async_client.get(f"/app/invites/{raw_token}")
    assert preview_res.status_code == 200
    assert preview_res.json()["org_name"] == org.name
    assert preview_res.json()["org_role"] == "member"

    # 3. New user sign up with invite token
    new_email = fake.email().lower()
    join_res = await async_client.post(
        "/app/auth/sign-up",
        json={
            "first_name": "Bob",
            "last_name": "Builder",
            "email": new_email,
            "password": "SecurePassword2!",
            "invite_token": raw_token,
        },
    )
    assert join_res.status_code == 201
    join_data = join_res.json()
    assert join_data["org"]["id"] == str(org.id)
    assert join_data["membership"]["org_role"] == "member"

    # 4. Invite cannot be reused (single use)
    reuse_res = await async_client.post(
        "/app/auth/sign-up",
        json={
            "first_name": "Charlie",
            "last_name": "Brown",
            "email": fake.email().lower(),
            "password": "SecurePassword3!",
            "invite_token": raw_token,
        },
    )
    assert reuse_res.status_code == 404


# ---------------------------------------------------------------------------
# Organization & Member Management Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_org_members_and_roles(async_client, session_factory):
    async with session_factory() as session:
        org, owner, owner_m = await _create_org_with_owner(session)
        user_b = await _create_user(session)
        member_b = Membership(org_id=org.id, user_id=user_b.id, org_role="member")
        session.add(member_b)
        await session.commit()
        member_b_id = member_b.id

    async_client.cookies.set("access_token", _auth_cookie(owner.id, org.id))

    # List members
    members_res = await async_client.get("/app/org/members")
    assert members_res.status_code == 200
    assert len(members_res.json()) == 2

    # Promote member to admin
    promote_res = await async_client.patch(
        f"/app/org/members/{member_b_id}",
        json={"org_role": "admin"},
    )
    assert promote_res.status_code == 200
    assert promote_res.json()["org_role"] == "admin"

    # Demoting last owner fails with 400
    demote_res = await async_client.patch(
        f"/app/org/members/{owner_m.id}",
        json={"org_role": "member"},
    )
    assert demote_res.status_code == 400
    assert demote_res.json()["detail"][0]["type"] == "last_owner"

    # Remove member
    del_res = await async_client.delete(f"/app/org/members/{member_b_id}")
    assert del_res.status_code == 200

    # Removing last owner fails with 400
    del_owner_res = await async_client.delete(f"/app/org/members/{owner_m.id}")
    assert del_owner_res.status_code == 400
    assert del_owner_res.json()["detail"][0]["type"] == "last_owner"


# ---------------------------------------------------------------------------
# Team Management Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_team_crud_and_members(async_client, session_factory):
    async with session_factory() as session:
        org, owner, owner_m = await _create_org_with_owner(session)
        user_dev = await _create_user(session)
        member_dev = Membership(org_id=org.id, user_id=user_dev.id, org_role="member")
        session.add(member_dev)
        await session.commit()
        member_dev_id = member_dev.id

    async_client.cookies.set("access_token", _auth_cookie(owner.id, org.id))

    # 1. Create team
    create_res = await async_client.post(
        "/app/teams",
        json={"name": "Core Engineering", "lead_membership_id": str(owner_m.id)},
    )
    assert create_res.status_code == 201
    team_data = create_res.json()
    team_id = team_data["id"]
    assert team_data["name"] == "Core Engineering"
    assert team_data["lead_membership_id"] == str(owner_m.id)

    # 2. Add dev to team
    add_m_res = await async_client.post(
        f"/app/teams/{team_id}/members",
        json={"membership_id": str(member_dev_id)},
    )
    assert add_m_res.status_code == 201

    # 3. Get team details
    detail_res = await async_client.get(f"/app/teams/{team_id}")
    assert detail_res.status_code == 200
    assert len(detail_res.json()["members"]) == 2

    # 4. Remove dev from team
    remove_m_res = await async_client.delete(
        f"/app/teams/{team_id}/members/{member_dev_id}"
    )
    assert remove_m_res.status_code == 200

    # 5. Delete team
    delete_res = await async_client.delete(f"/app/teams/{team_id}")
    assert delete_res.status_code == 200

    # 6. Team no longer found (404)
    get_after_del = await async_client.get(f"/app/teams/{team_id}")
    assert get_after_del.status_code == 404


# ---------------------------------------------------------------------------
# Suspended Org & Deactivated User Token Invalidation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_suspended_org_token_rejected(async_client, session_factory):
    async with session_factory() as session:
        org, owner, _ = await _create_org_with_owner(session)
        await session.commit()
        org_id = org.id
        owner_id = owner.id

    token = _auth_cookie(owner_id, org_id)
    async_client.cookies.set("access_token", token)

    # Valid before suspension
    assert (await async_client.get("/app/org")).status_code == 200

    # Suspend organization
    async with session_factory() as session:
        from datetime import UTC, datetime
        o = await session.get(Organization, org_id)
        o.suspended_at = datetime.now(UTC)
        await session.commit()

    # Token issued before suspension MUST stop working immediately (401)
    res = await async_client.get("/app/org")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_deactivated_user_token_rejected(async_client, session_factory):
    async with session_factory() as session:
        org, owner, _ = await _create_org_with_owner(session)
        await session.commit()
        user_id = owner.id
        org_id = org.id

    token = _auth_cookie(user_id, org_id)
    async_client.cookies.set("access_token", token)

    # Valid before deactivation
    assert (await async_client.get("/app/org")).status_code == 200

    # Deactivate user
    async with session_factory() as session:
        u = await session.get(User, user_id)
        u.is_active = False
        await session.commit()

    # Token issued before deactivation MUST stop working immediately (401)
    res = await async_client.get("/app/org")
    assert res.status_code == 401
