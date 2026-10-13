from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.app.access import CurrentAuth
from app.api.app.schemas import (
    InviteCreateRequest,
    InviteResponse,
    MemberWithUserResponse,
    OrganizationResponse,
    OrganizationUpdateRequest,
    UpdateMemberRoleRequest,
    UserResponse,
)
from app.database import DBSession
from app.schemas import MessageResponse
from app.services.invites import InviteService
from app.services.organizations import OrganizationService
from app.tenancy import require_org_admin

router = APIRouter(prefix="/org", tags=["organization"])


@router.get("", response_model=OrganizationResponse)
async def get_current_organization(ctx: CurrentAuth) -> OrganizationResponse:
    return OrganizationResponse.model_validate(ctx.org)


@router.patch("", response_model=OrganizationResponse)
async def update_organization(
    body: OrganizationUpdateRequest, ctx: CurrentAuth, session: DBSession
) -> OrganizationResponse:
    require_org_admin(ctx)
    org_service = OrganizationService(session)
    updated_org = await org_service.update_organization(
        ctx.org.id, name=body.name, slug=body.slug
    )
    await session.commit()
    return OrganizationResponse.model_validate(updated_org)


@router.get("/members", response_model=list[MemberWithUserResponse])
async def list_organization_members(
    ctx: CurrentAuth, session: DBSession
) -> list[MemberWithUserResponse]:
    org_service = OrganizationService(session)
    memberships = await org_service.list_members(ctx.org.id)
    return [
        MemberWithUserResponse(
            id=m.id,
            created_at=m.created_at,
            org_role=m.org_role,
            user=UserResponse.model_validate(m.user),
        )
        for m in memberships
    ]


@router.patch("/members/{membership_id}", response_model=MemberWithUserResponse)
async def update_member_role(
    membership_id: uuid.UUID,
    body: UpdateMemberRoleRequest,
    ctx: CurrentAuth,
    session: DBSession,
) -> MemberWithUserResponse:
    org_service = OrganizationService(session)
    updated_membership = await org_service.update_member_role(
        org_id=ctx.org.id,
        membership_id=membership_id,
        new_role=body.org_role,
        actor_ctx=ctx,
    )
    await session.commit()
    return MemberWithUserResponse(
        id=updated_membership.id,
        created_at=updated_membership.created_at,
        org_role=updated_membership.org_role,
        user=UserResponse.model_validate(updated_membership.user),
    )


@router.delete("/members/{membership_id}")
async def remove_member(
    membership_id: uuid.UUID, ctx: CurrentAuth, session: DBSession
) -> MessageResponse:
    org_service = OrganizationService(session)
    await org_service.remove_member(
        org_id=ctx.org.id,
        membership_id=membership_id,
        actor_ctx=ctx,
    )
    await session.commit()
    return MessageResponse(message="Member removed successfully")


@router.get("/invites", response_model=list[InviteResponse])
async def list_invites(
    ctx: CurrentAuth, session: DBSession
) -> list[InviteResponse]:
    require_org_admin(ctx)
    invite_service = InviteService(session)
    invites = await invite_service.list_invites(ctx.org.id)
    return [
        InviteResponse(
            id=i.id,
            created_at=i.created_at,
            org_id=i.org_id,
            org_role=i.org_role,
            expires_at=i.expires_at,
            created_by=(
                MemberWithUserResponse(
                    id=i.created_by.id,
                    created_at=i.created_by.created_at,
                    org_role=i.created_by.org_role,
                    user=UserResponse.model_validate(i.created_by.user),
                )
                if i.created_by and i.created_by.user
                else None
            ),
        )
        for i in invites
    ]


@router.post("/invites", response_model=InviteResponse, status_code=status.HTTP_201_CREATED)
async def create_invite(
    body: InviteCreateRequest, ctx: CurrentAuth, session: DBSession
) -> InviteResponse:
    require_org_admin(ctx)
    invite_service = InviteService(session)
    invite, raw_token = await invite_service.create_invite(
        org_id=ctx.org.id,
        org_role=body.org_role,
        expires_in_days=body.expires_in_days,
        created_by_id=ctx.membership.id,
    )
    await session.commit()
    return InviteResponse(
        id=invite.id,
        created_at=invite.created_at,
        org_id=invite.org_id,
        org_role=invite.org_role,
        expires_at=invite.expires_at,
        raw_token=raw_token,
        created_by=MemberWithUserResponse(
            id=ctx.membership.id,
            created_at=ctx.membership.created_at,
            org_role=ctx.membership.org_role,
            user=UserResponse.model_validate(ctx.user),
        ),
    )


@router.delete("/invites/{invite_id}")
async def revoke_invite(
    invite_id: uuid.UUID, ctx: CurrentAuth, session: DBSession
) -> MessageResponse:
    require_org_admin(ctx)
    invite_service = InviteService(session)
    await invite_service.revoke_invite(ctx.org.id, invite_id)
    await session.commit()
    return MessageResponse(message="Invite revoked successfully")
