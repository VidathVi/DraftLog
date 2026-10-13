from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.app.access import CurrentAuth
from app.api.app.schemas import (
    AddTeamMemberRequest,
    MemberWithUserResponse,
    TeamCreateRequest,
    TeamDetailResponse,
    TeamMemberItem,
    TeamResponse,
    TeamUpdateRequest,
    UserResponse,
)
from app.database import DBSession
from app.models import Team
from app.schemas import MessageResponse
from app.services.teams import TeamService
from app.tenancy import require_org_admin

router = APIRouter(prefix="/teams", tags=["teams"])


def _format_team_response(team: Team) -> TeamResponse:
    lead_response = None
    if team.lead and team.lead.user:
        lead_response = MemberWithUserResponse(
            id=team.lead.id,
            created_at=team.lead.created_at,
            org_role=team.lead.org_role,
            user=UserResponse.model_validate(team.lead.user),
        )

    return TeamResponse(
        id=team.id,
        created_at=team.created_at,
        org_id=team.org_id,
        name=team.name,
        lead_membership_id=team.lead_membership_id,
        lead=lead_response,
        member_count=len(team.members),
    )


@router.get("", response_model=list[TeamResponse])
async def list_teams(ctx: CurrentAuth, session: DBSession) -> list[TeamResponse]:
    team_service = TeamService(session)
    teams = await team_service.list_teams(ctx.org.id)
    return [_format_team_response(t) for t in teams]


@router.post("", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team(
    body: TeamCreateRequest, ctx: CurrentAuth, session: DBSession
) -> TeamResponse:
    require_org_admin(ctx)
    team_service = TeamService(session)
    team = await team_service.create_team(
        org_id=ctx.org.id,
        name=body.name,
        lead_membership_id=body.lead_membership_id,
    )
    await session.commit()
    return _format_team_response(team)


@router.get("/{team_id}", response_model=TeamDetailResponse)
async def get_team(
    team_id: uuid.UUID, ctx: CurrentAuth, session: DBSession
) -> TeamDetailResponse:
    team_service = TeamService(session)
    team = await team_service.get_team(ctx.org.id, team_id)

    lead_response = None
    if team.lead and team.lead.user:
        lead_response = MemberWithUserResponse(
            id=team.lead.id,
            created_at=team.lead.created_at,
            org_role=team.lead.org_role,
            user=UserResponse.model_validate(team.lead.user),
        )

    members_list = [
        TeamMemberItem(
            membership_id=tm.membership_id,
            user=UserResponse.model_validate(tm.membership.user),
            org_role=tm.membership.org_role,
        )
        for tm in team.members
        if tm.membership and tm.membership.user
    ]

    return TeamDetailResponse(
        id=team.id,
        created_at=team.created_at,
        org_id=team.org_id,
        name=team.name,
        lead_membership_id=team.lead_membership_id,
        lead=lead_response,
        members=members_list,
    )


@router.patch("/{team_id}", response_model=TeamResponse)
async def update_team(
    team_id: uuid.UUID,
    body: TeamUpdateRequest,
    ctx: CurrentAuth,
    session: DBSession,
) -> TeamResponse:
    require_org_admin(ctx)
    team_service = TeamService(session)
    team = await team_service.update_team(
        org_id=ctx.org.id,
        team_id=team_id,
        name=body.name,
        lead_membership_id=body.lead_membership_id,
        clear_lead=body.clear_lead,
    )
    await session.commit()
    return _format_team_response(team)


@router.delete("/{team_id}")
async def delete_team(
    team_id: uuid.UUID, ctx: CurrentAuth, session: DBSession
) -> MessageResponse:
    require_org_admin(ctx)
    team_service = TeamService(session)
    await team_service.delete_team(org_id=ctx.org.id, team_id=team_id)
    await session.commit()
    return MessageResponse(message="Team deleted successfully")


@router.get("/{team_id}/members", response_model=list[TeamMemberItem])
async def list_team_members(
    team_id: uuid.UUID, ctx: CurrentAuth, session: DBSession
) -> list[TeamMemberItem]:
    team_service = TeamService(session)
    members = await team_service.list_team_members(ctx.org.id, team_id)
    return [
        TeamMemberItem(
            membership_id=tm.membership_id,
            user=UserResponse.model_validate(tm.membership.user),
            org_role=tm.membership.org_role,
        )
        for tm in members
        if tm.membership and tm.membership.user
    ]


@router.post(
    "/{team_id}/members",
    response_model=TeamMemberItem,
    status_code=status.HTTP_201_CREATED,
)
async def add_team_member(
    team_id: uuid.UUID,
    body: AddTeamMemberRequest,
    ctx: CurrentAuth,
    session: DBSession,
) -> TeamMemberItem:
    require_org_admin(ctx)
    team_service = TeamService(session)
    tm = await team_service.add_team_member(
        org_id=ctx.org.id,
        team_id=team_id,
        membership_id=body.membership_id,
    )
    await session.commit()
    return TeamMemberItem(
        membership_id=tm.membership_id,
        user=UserResponse.model_validate(tm.membership.user),
        org_role=tm.membership.org_role,
    )


@router.delete("/{team_id}/members/{membership_id}")
async def remove_team_member(
    team_id: uuid.UUID,
    membership_id: uuid.UUID,
    ctx: CurrentAuth,
    session: DBSession,
) -> MessageResponse:
    require_org_admin(ctx)
    team_service = TeamService(session)
    await team_service.remove_team_member(
        org_id=ctx.org.id,
        team_id=team_id,
        membership_id=membership_id,
    )
    await session.commit()
    return MessageResponse(message="Team member removed successfully")
