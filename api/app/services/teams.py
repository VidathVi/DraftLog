from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions import ConflictException, ResourceNotFoundException
from app.models import Membership, Team, TeamMember


class TeamService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_teams(self, org_id: uuid.UUID) -> Sequence[Team]:
        result = await self.session.execute(
            select(Team)
            .options(
                selectinload(Team.lead).selectinload(Membership.user),
                selectinload(Team.members).selectinload(TeamMember.membership).selectinload(Membership.user),
            )
            .where(Team.org_id == org_id)
            .order_by(Team.name.asc())
        )
        return result.scalars().all()

    async def get_team(self, org_id: uuid.UUID, team_id: uuid.UUID) -> Team:
        result = await self.session.execute(
            select(Team)
            .options(
                selectinload(Team.lead).selectinload(Membership.user),
                selectinload(Team.members).selectinload(TeamMember.membership).selectinload(Membership.user),
            )
            .where(
                Team.id == team_id,
                Team.org_id == org_id,
            )
        )
        team = result.scalars().first()
        if team is None:
            raise ResourceNotFoundException("Team not found")
        return team

    async def create_team(
        self,
        *,
        org_id: uuid.UUID,
        name: str,
        lead_membership_id: uuid.UUID | None = None,
    ) -> Team:
        if lead_membership_id is not None:
            lead_in_org = await self.session.scalar(
                select(Membership.id).where(
                    Membership.id == lead_membership_id,
                    Membership.org_id == org_id,
                )
            )
            if lead_in_org is None:
                raise ResourceNotFoundException("Team lead not found in organization")

        team = Team(
            org_id=org_id,
            name=name,
            lead_membership_id=lead_membership_id,
        )
        self.session.add(team)
        await self.session.flush()

        # If lead is assigned, automatically add them to team_members
        if lead_membership_id is not None:
            team_member = TeamMember(
                team_id=team.id,
                membership_id=lead_membership_id,
            )
            self.session.add(team_member)
            await self.session.flush()

        return await self.get_team(org_id, team.id)

    async def update_team(
        self,
        *,
        org_id: uuid.UUID,
        team_id: uuid.UUID,
        name: str | None = None,
        lead_membership_id: uuid.UUID | None = None,
        clear_lead: bool = False,
    ) -> Team:
        team = await self.get_team(org_id, team_id)

        if name is not None:
            team.name = name

        if clear_lead:
            team.lead_membership_id = None
        elif lead_membership_id is not None:
            lead_in_org = await self.session.scalar(
                select(Membership.id).where(
                    Membership.id == lead_membership_id,
                    Membership.org_id == org_id,
                )
            )
            if lead_in_org is None:
                raise ResourceNotFoundException("Team lead not found in organization")
            team.lead_membership_id = lead_membership_id

            # Ensure lead is in team_members
            is_member = await self.session.scalar(
                select(TeamMember.id).where(
                    TeamMember.team_id == team.id,
                    TeamMember.membership_id == lead_membership_id,
                )
            )
            if is_member is None:
                self.session.add(
                    TeamMember(team_id=team.id, membership_id=lead_membership_id)
                )

        await self.session.flush()
        return await self.get_team(org_id, team.id)

    async def delete_team(self, *, org_id: uuid.UUID, team_id: uuid.UUID) -> None:
        team = await self.get_team(org_id, team_id)
        await self.session.delete(team)
        await self.session.flush()

    async def list_team_members(
        self, org_id: uuid.UUID, team_id: uuid.UUID
    ) -> Sequence[TeamMember]:
        await self.get_team(org_id, team_id)  # verifies team belongs to org

        result = await self.session.execute(
            select(TeamMember)
            .options(selectinload(TeamMember.membership).selectinload(Membership.user))
            .where(TeamMember.team_id == team_id)
            .order_by(TeamMember.created_at.asc())
        )
        return result.scalars().all()

    async def add_team_member(
        self, *, org_id: uuid.UUID, team_id: uuid.UUID, membership_id: uuid.UUID
    ) -> TeamMember:
        await self.get_team(org_id, team_id)  # verifies team belongs to org

        # Verify membership belongs to org
        member_in_org = await self.session.scalar(
            select(Membership.id).where(
                Membership.id == membership_id,
                Membership.org_id == org_id,
            )
        )
        if member_in_org is None:
            raise ResourceNotFoundException("Member not found in organization")

        existing = await self.session.scalar(
            select(TeamMember.id).where(
                TeamMember.team_id == team_id,
                TeamMember.membership_id == membership_id,
            )
        )
        if existing is not None:
            raise ConflictException("Member is already in this team")

        team_member = TeamMember(team_id=team_id, membership_id=membership_id)
        self.session.add(team_member)
        await self.session.flush()

        result = await self.session.execute(
            select(TeamMember)
            .options(selectinload(TeamMember.membership).selectinload(Membership.user))
            .where(TeamMember.id == team_member.id)
        )
        return result.scalars().one()

    async def remove_team_member(
        self, *, org_id: uuid.UUID, team_id: uuid.UUID, membership_id: uuid.UUID
    ) -> None:
        await self.get_team(org_id, team_id)  # verifies team belongs to org

        result = await self.session.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.membership_id == membership_id,
            )
        )
        item = result.scalars().first()
        if item is None:
            raise ResourceNotFoundException("Team member not found")

        await self.session.delete(item)
        await self.session.flush()
