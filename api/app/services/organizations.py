from __future__ import annotations

import re
import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions import ConflictException, ResourceNotFoundException
from app.models import Membership, Organization
from app.tenancy import (
    AuthContext,
    check_can_change_role,
    check_can_remove_member,
)


def _slugify(text: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[-\s]+", "-", slug).strip("-")
    return slug or "org"


class OrganizationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_organization(self, org_id: uuid.UUID) -> Organization:
        """Fetch an organization by ID. Rejects if not found or suspended."""
        result = await self.session.execute(
            select(Organization).where(Organization.id == org_id)
        )
        org = result.scalars().first()
        if org is None or org.suspended_at is not None:
            raise ResourceNotFoundException("Organization not found")
        return org

    async def create_organization(
        self,
        *,
        name: str,
        slug: str | None = None,
    ) -> Organization:
        base_slug = slug or _slugify(name)
        candidate_slug = base_slug
        counter = 1

        while True:
            existing = await self.session.scalar(
                select(Organization.id).where(Organization.slug == candidate_slug)
            )
            if existing is None:
                break
            candidate_slug = f"{base_slug}-{counter}"
            counter += 1

        org = Organization(name=name, slug=candidate_slug)
        self.session.add(org)
        await self.session.flush()
        return org

    async def update_organization(
        self,
        org_id: uuid.UUID,
        *,
        name: str | None = None,
        slug: str | None = None,
    ) -> Organization:
        org = await self.get_organization(org_id)

        if name is not None:
            org.name = name

        if slug is not None and slug != org.slug:
            existing = await self.session.scalar(
                select(Organization.id).where(
                    Organization.slug == slug, Organization.id != org_id
                )
            )
            if existing is not None:
                raise ConflictException("Organization slug already taken", field="slug")
            org.slug = slug

        await self.session.flush()
        return org

    async def list_members(self, org_id: uuid.UUID) -> Sequence[Membership]:
        """List all memberships in the organization, with user details preloaded."""
        result = await self.session.execute(
            select(Membership)
            .options(selectinload(Membership.user))
            .where(Membership.org_id == org_id)
            .order_by(Membership.created_at.asc())
        )
        return result.scalars().all()

    async def get_membership(
        self, org_id: uuid.UUID, membership_id: uuid.UUID
    ) -> Membership:
        """Fetch a membership strictly scoped by org_id."""
        result = await self.session.execute(
            select(Membership)
            .options(selectinload(Membership.user))
            .where(
                Membership.id == membership_id,
                Membership.org_id == org_id,
            )
        )
        membership = result.scalars().first()
        if membership is None:
            raise ResourceNotFoundException("Member not found")
        return membership

    async def count_owners(self, org_id: uuid.UUID) -> int:
        count = await self.session.scalar(
            select(func.count())
            .select_from(Membership)
            .where(
                Membership.org_id == org_id,
                Membership.org_role == "owner",
            )
        )
        return count or 0

    async def add_member(
        self,
        *,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str = "member",
    ) -> Membership:
        existing = await self.session.scalar(
            select(Membership.id).where(
                Membership.org_id == org_id,
                Membership.user_id == user_id,
            )
        )
        if existing is not None:
            raise ConflictException("User is already a member of this organization")

        membership = Membership(
            org_id=org_id,
            user_id=user_id,
            org_role=role,
        )
        self.session.add(membership)
        await self.session.flush()
        return membership

    async def update_member_role(
        self,
        *,
        org_id: uuid.UUID,
        membership_id: uuid.UUID,
        new_role: str,
        actor_ctx: AuthContext,
    ) -> Membership:
        membership = await self.get_membership(org_id, membership_id)
        owner_count = await self.count_owners(org_id)

        # Enforce Phase 2 permission matrix rules
        check_can_change_role(
            actor_ctx=actor_ctx,
            target_membership=membership,
            new_role=new_role,
            owner_count=owner_count,
        )

        membership.org_role = new_role
        await self.session.flush()
        return membership

    async def remove_member(
        self,
        *,
        org_id: uuid.UUID,
        membership_id: uuid.UUID,
        actor_ctx: AuthContext,
    ) -> None:
        membership = await self.get_membership(org_id, membership_id)
        owner_count = await self.count_owners(org_id)

        # Enforce Phase 2 permission matrix rules
        check_can_remove_member(
            actor_ctx=actor_ctx,
            target_membership=membership,
            owner_count=owner_count,
        )

        await self.session.delete(membership)
        await self.session.flush()
