from __future__ import annotations

import hashlib
import secrets
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions import ConflictException, ResourceNotFoundException
from app.models import Invite, Membership, Organization


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class InviteService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_invite(
        self,
        *,
        org_id: uuid.UUID,
        org_role: str = "member",
        expires_in_days: int = 7,
        created_by_id: uuid.UUID | None = None,
    ) -> tuple[Invite, str]:
        raw_token = secrets.token_urlsafe(32)
        token_hash = _hash_token(raw_token)
        expires_at = datetime.now(UTC) + timedelta(days=expires_in_days)

        invite = Invite(
            org_id=org_id,
            token_hash=token_hash,
            org_role=org_role,
            expires_at=expires_at,
            created_by_id=created_by_id,
        )
        self.session.add(invite)
        await self.session.flush()
        return invite, raw_token

    async def get_invite_by_raw_token(self, raw_token: str) -> Invite:
        token_hash = _hash_token(raw_token)
        result = await self.session.execute(
            select(Invite)
            .options(
                selectinload(Invite.organization),
                selectinload(Invite.created_by).selectinload(Membership.user),
            )
            .where(Invite.token_hash == token_hash)
        )
        invite = result.scalars().first()
        now = datetime.now(UTC)

        if invite is None or invite.used_at is not None:
            raise ResourceNotFoundException("Invite link is invalid or has expired.")

        expires_at = invite.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)

        if expires_at < now or (
            invite.organization and invite.organization.suspended_at is not None
        ):
            raise ResourceNotFoundException("Invite link is invalid or has expired.")

        return invite

    async def list_invites(self, org_id: uuid.UUID) -> Sequence[Invite]:
        now = datetime.now(UTC)
        result = await self.session.execute(
            select(Invite)
            .options(selectinload(Invite.created_by).selectinload(Membership.user))
            .where(
                Invite.org_id == org_id,
                Invite.used_at.is_(None),
                Invite.expires_at > now,
            )
            .order_by(Invite.created_at.desc())
        )
        return result.scalars().all()

    async def revoke_invite(self, org_id: uuid.UUID, invite_id: uuid.UUID) -> None:
        result = await self.session.execute(
            select(Invite).where(
                Invite.id == invite_id,
                Invite.org_id == org_id,
            )
        )
        invite = result.scalars().first()
        if invite is None:
            raise ResourceNotFoundException("Invite not found")
        await self.session.delete(invite)
        await self.session.flush()

    async def accept_invite(
        self, raw_token: str, user_id: uuid.UUID
    ) -> tuple[Membership, Organization]:
        invite = await self.get_invite_by_raw_token(raw_token)

        # Check if already a member
        existing_membership = await self.session.scalar(
            select(Membership.id).where(
                Membership.org_id == invite.org_id,
                Membership.user_id == user_id,
            )
        )
        if existing_membership is not None:
            raise ConflictException("You are already a member of this organization.")

        membership = Membership(
            org_id=invite.org_id,
            user_id=user_id,
            org_role=invite.org_role,
        )
        self.session.add(membership)

        invite.used_at = datetime.now(UTC)
        await self.session.flush()

        return membership, invite.organization
