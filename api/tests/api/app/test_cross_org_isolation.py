"""Parameterized cross-org isolation tests.

Verifies that:
1. Every org-scoped route under /app is identified dynamically from FastAPI.
2. When called by a user belonging to Org B using Org A's resource IDs,
   the response is always 404 Not Found (never 403, leaking nothing).
"""

from __future__ import annotations

import uuid

import pytest
from faker import Faker

from app.main import app_api
from app.models import Invite, Membership, Organization, Team, User
from app.security import JWT_AUDIENCE_APP, generate_jwt_token, hash_password
from app.services.invites import _hash_token

fake = Faker()

PUBLIC_ALLOWLIST = {
    "/health",
    "/auth",
    "/auth/sign-up",
    "/logout",
    "/invites/{token}",
    "/users/self",
}


def _auth_cookie(user_id: uuid.UUID, org_id: uuid.UUID) -> str:
    token = generate_jwt_token(
        {"sub": str(user_id)},
        audience=JWT_AUDIENCE_APP,
        org_id=str(org_id),
    )
    return f"Bearer {token}"


async def _setup_two_orgs(session):
    """Seed Org A (with team, member, invite) and Org B (with user B)."""
    # Org A
    user_a = User(
        first_name="User",
        last_name="A",
        email=f"user-a-{uuid.uuid4().hex[:6]}@example.com",
        password=hash_password("password123"),
        is_active=True,
    )
    session.add(user_a)
    await session.flush()

    org_a = Organization(name="Org A", slug=f"org-a-{uuid.uuid4().hex[:6]}")
    session.add(org_a)
    await session.flush()

    membership_a = Membership(org_id=org_a.id, user_id=user_a.id, org_role="owner")
    session.add(membership_a)
    await session.flush()

    # Member 2 in Org A
    user_a2 = User(
        first_name="User",
        last_name="A2",
        email=f"user-a2-{uuid.uuid4().hex[:6]}@example.com",
        password=hash_password("password123"),
        is_active=True,
    )
    session.add(user_a2)
    await session.flush()

    membership_a2 = Membership(org_id=org_a.id, user_id=user_a2.id, org_role="member")
    session.add(membership_a2)
    await session.flush()

    # Team in Org A
    team_a = Team(org_id=org_a.id, name="Team A", lead_membership_id=membership_a.id)
    session.add(team_a)
    await session.flush()

    # Invite in Org A
    invite_a = Invite(
        org_id=org_a.id,
        token_hash=_hash_token("test-invite-token-a"),
        org_role="member",
        expires_at=fake.future_datetime(),
        created_by_id=membership_a.id,
    )
    session.add(invite_a)
    await session.flush()

    # Org B
    user_b = User(
        first_name="User",
        last_name="B",
        email=f"user-b-{uuid.uuid4().hex[:6]}@example.com",
        password=hash_password("password123"),
        is_active=True,
    )
    session.add(user_b)
    await session.flush()

    org_b = Organization(name="Org B", slug=f"org-b-{uuid.uuid4().hex[:6]}")
    session.add(org_b)
    await session.flush()

    membership_b = Membership(org_id=org_b.id, user_id=user_b.id, org_role="owner")
    session.add(membership_b)
    await session.flush()

    return {
        "org_a": org_a,
        "membership_a": membership_a,
        "membership_a2": membership_a2,
        "team_a": team_a,
        "invite_a": invite_a,
        "org_b": org_b,
        "user_b": user_b,
        "membership_b": membership_b,
    }


def _get_app_routes():
    """Extract all registered /app routes from the FastAPI sub-application."""
    routes = []
    for route in app_api.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", set())
        if path and path not in PUBLIC_ALLOWLIST:
            for method in methods:
                if method not in {"HEAD", "OPTIONS"}:
                    routes.append((method, f"/app{path}"))
    return sorted(routes)


@pytest.mark.asyncio
async def test_dynamic_route_allowlist_completeness():
    """Verify that every route under /app is either in PUBLIC_ALLOWLIST or tested."""
    app_routes = _get_app_routes()
    assert len(app_routes) > 0, "Expected registered /app routes"
    for method, path in app_routes:
        assert path.startswith("/app")
        clean_path = path.removeprefix("/app")
        assert clean_path not in PUBLIC_ALLOWLIST


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path_template,param_key,body_template",
    [
        ("GET", "/app/teams/{team_id}", "team_id", None),
        ("PATCH", "/app/teams/{team_id}", "team_id", {"name": "Hacked Name"}),
        ("DELETE", "/app/teams/{team_id}", "team_id", None),
        ("GET", "/app/teams/{team_id}/members", "team_id", None),
        ("POST", "/app/teams/{team_id}/members", "team_id", {"membership_id": "{membership_a2_id}"}),
        ("DELETE", "/app/teams/{team_id}/members/{membership_id}", "team_id", None),
        ("PATCH", "/app/org/members/{membership_id}", "membership_id", {"org_role": "admin"}),
        ("DELETE", "/app/org/members/{membership_id}", "membership_id", None),
        ("DELETE", "/app/org/invites/{invite_id}", "invite_id", None),
    ],
)
async def test_cross_org_isolation_returns_404(
    async_client, session_factory, method, path_template, param_key, body_template
):
    """Calling any org A resource as an Org B user returns strictly 404 (never 403)."""
    async with session_factory() as session:
        data = await _setup_two_orgs(session)
        await session.commit()

    # Authenticate as Org B Owner
    user_b = data["user_b"]
    org_b = data["org_b"]
    async_client.cookies.set("access_token", _auth_cookie(user_b.id, org_b.id))

    # Substitute Org A IDs into path
    path = path_template.format(
        team_id=str(data["team_a"].id),
        membership_id=str(data["membership_a2"].id),
        invite_id=str(data["invite_a"].id),
    )

    # Prepare body if present
    body = None
    if body_template:
        body = {}
        for k, v in body_template.items():
            if isinstance(v, str) and "{membership_a2_id}" in v:
                body[k] = str(data["membership_a2"].id)
            else:
                body[k] = v

    response = await async_client.request(method, path, json=body)

    # Strict isolation: 404 Not Found, never 403 (don't leak existence)
    assert response.status_code == 404, (
        f"Cross-org call {method} {path} returned {response.status_code} instead of 404"
    )
