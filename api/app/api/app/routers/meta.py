from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.api.app.schemas import (
    AuthRequest,
    AuthResponse,
    InvitePublicResponse,
    MembershipResponse,
    OrganizationResponse,
    SignUpRequest,
    UserResponse,
)
from app.config import settings
from app.database import DBSession
from app.exceptions import APIException
from app.logging import logger
from app.models import Membership, Organization, User
from app.schemas import HealthCheckResponse, MessageResponse
from app.security import (
    JWT_AUDIENCE_APP,
    generate_jwt_token,
    verify_password,
)
from app.services.invites import InviteService
from app.services.organizations import OrganizationService
from app.services.users import UserService

router = APIRouter()


@router.get("/health", tags=["meta"])
async def health(session: DBSession, response: Response) -> HealthCheckResponse:
    try:
        await session.execute(text("SELECT 1"))
        return HealthCheckResponse(status="healthy")
    except Exception:
        logger.exception("Health check failed")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthCheckResponse(status="unhealthy")


@router.post("/auth", tags=["auth"])
async def auth(
    auth_request: AuthRequest, session: DBSession, response: Response
) -> AuthResponse:
    result = await session.execute(
        select(User)
        .options(
            selectinload(User.memberships).selectinload(Membership.organization)
        )
        .where(User.email == auth_request.email.lower())
    )
    user = result.scalars().first()

    if (
        user is None
        or not user.is_active
        or user.password is None
        or not verify_password(auth_request.password, user.password)
    ):
        raise APIException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="INVALID_CREDENTIALS",
            message="Incorrect username or password",
        )

    # Resolve active organization
    chosen_membership: Membership | None = None
    chosen_org: Organization | None = None

    active_memberships = [
        m for m in user.memberships
        if m.organization and m.organization.suspended_at is None
    ]

    if auth_request.org_id is not None:
        matched = [m for m in active_memberships if m.org_id == auth_request.org_id]
        if not matched:
            raise APIException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                code="INVALID_ORG",
                message="User does not have access to the specified organization",
            )
        chosen_membership = matched[0]
        chosen_org = chosen_membership.organization
    elif active_memberships:
        chosen_membership = active_memberships[0]
        chosen_org = chosen_membership.organization

    org_id_str = str(chosen_org.id) if chosen_org else None
    access_token = generate_jwt_token(
        {"sub": str(user.id)},
        audience=JWT_AUDIENCE_APP,
        org_id=org_id_str,
    )

    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        samesite="lax",
        secure=settings.SECURE_COOKIE,
        httponly=True,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    return AuthResponse(
        access_token=access_token,
        user=UserResponse.model_validate(user),
        org=OrganizationResponse.model_validate(chosen_org) if chosen_org else None,
        membership=MembershipResponse.model_validate(chosen_membership) if chosen_membership else None,
    )


@router.post("/auth/sign-up", tags=["auth"], status_code=status.HTTP_201_CREATED)
async def sign_up(
    body: SignUpRequest, session: DBSession, response: Response
) -> AuthResponse:
    if not body.org_name and not body.invite_token:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="MISSING_ORGANIZATION_INFO",
            message="Please provide an organization name to create an org, or an invite token to join an existing org.",
        )

    user_service = UserService(session)
    org_service = OrganizationService(session)
    invite_service = InviteService(session)

    # 1. Create user
    user = await user_service.create_user(
        first_name=body.first_name,
        last_name=body.last_name,
        email=body.email,
        password=body.password,
    )

    # 2. Join via invite or create new org
    if body.invite_token:
        membership, org = await invite_service.accept_invite(
            body.invite_token, user.id
        )
    else:
        assert body.org_name is not None
        org = await org_service.create_organization(name=body.org_name)
        membership = await org_service.add_member(
            org_id=org.id,
            user_id=user.id,
            role="owner",
        )

    # Router commits transaction per AGENTS.md conventions
    await session.commit()

    access_token = generate_jwt_token(
        {"sub": str(user.id)},
        audience=JWT_AUDIENCE_APP,
        org_id=str(org.id),
    )

    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        samesite="lax",
        secure=settings.SECURE_COOKIE,
        httponly=True,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    return AuthResponse(
        access_token=access_token,
        user=UserResponse.model_validate(user),
        org=OrganizationResponse.model_validate(org),
        membership=MembershipResponse.model_validate(membership),
    )


@router.get("/invites/{token}", tags=["invites"])
async def preview_invite(token: str, session: DBSession) -> InvitePublicResponse:
    invite_service = InviteService(session)
    invite = await invite_service.get_invite_by_raw_token(token)

    inviter_name = None
    if invite.created_by and invite.created_by.user:
        inviter_name = f"{invite.created_by.user.first_name} {invite.created_by.user.last_name}".strip()

    return InvitePublicResponse(
        org_name=invite.organization.name,
        org_slug=invite.organization.slug,
        org_role=invite.org_role,
        inviter_name=inviter_name,
        expires_at=invite.expires_at,
    )


@router.post("/logout", tags=["auth"])
async def logout(response: Response) -> MessageResponse:
    response.delete_cookie("access_token")
    return MessageResponse(message="Successfully logged out")
