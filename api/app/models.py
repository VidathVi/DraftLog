from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    types,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class IdMixin:
    # Mixin columns sort after the model's own columns by default; keep the
    # primary key first in generated migrations.
    id: Mapped[uuid.UUID] = mapped_column(
        types.Uuid, primary_key=True, default=uuid.uuid4, sort_order=-1
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=_utcnow, nullable=True
    )


# ---------------------------------------------------------------------------
# Core: Users
# ---------------------------------------------------------------------------


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    password: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationships
    memberships: Mapped[list[Membership]] = relationship(back_populates="user")


# ---------------------------------------------------------------------------
# Multi-tenancy: Organizations & Memberships
# ---------------------------------------------------------------------------


class Organization(IdMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    suspended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_active_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    memberships: Mapped[list[Membership]] = relationship(back_populates="organization")
    teams: Mapped[list[Team]] = relationship(back_populates="organization")
    invites: Mapped[list[Invite]] = relationship(back_populates="organization")


class Membership(IdMixin, TimestampMixin, Base):
    """Links a user to an organization with an org-level role.

    `org_role` is one of: "owner", "admin", "member".
    This is distinct from ``User.is_admin`` which is the platform staff flag.
    """

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("org_id", "user_id"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    org_role: Mapped[str] = mapped_column(
        String(50), nullable=False, default="member"
    )

    # Relationships
    organization: Mapped[Organization] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")


# ---------------------------------------------------------------------------
# Invites
# ---------------------------------------------------------------------------


class Invite(IdMixin, TimestampMixin, Base):
    """A single-use invite link to join an organization.

    The raw token is given to the invitee; only the SHA-256 hash is stored.
    """

    __tablename__ = "invites"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    org_role: Mapped[str] = mapped_column(
        String(50), nullable=False, default="member"
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("memberships.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    organization: Mapped[Organization] = relationship(back_populates="invites")
    created_by: Mapped[Membership | None] = relationship()


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------


class Team(IdMixin, TimestampMixin, Base):
    __tablename__ = "teams"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    lead_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("memberships.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Relationships
    organization: Mapped[Organization] = relationship(back_populates="teams")
    lead: Mapped[Membership | None] = relationship(
        foreign_keys=[lead_membership_id]
    )
    members: Mapped[list[TeamMember]] = relationship(back_populates="team")


class TeamMember(IdMixin, TimestampMixin, Base):
    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("team_id", "membership_id"),)

    team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    membership_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memberships.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Relationships
    team: Mapped[Team] = relationship(back_populates="members")
    membership: Mapped[Membership] = relationship()


# ---------------------------------------------------------------------------
# Plans & Tasks
# ---------------------------------------------------------------------------


class Plan(IdMixin, TimestampMixin, Base):
    """A weekly plan submitted by a team member.

    Status flow (enforced server-side):
        draft → submitted → approved → done
                submitted → draft (send-back, requires lead_comment)
    """

    __tablename__ = "plans"
    __table_args__ = (UniqueConstraint("membership_id", "week_monday"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    membership_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memberships.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    week_monday: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="draft"
    )
    lead_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationships
    organization: Mapped[Organization] = relationship()
    membership: Mapped[Membership] = relationship()
    team: Mapped[Team] = relationship()
    tasks: Mapped[list[Task]] = relationship(
        back_populates="plan", order_by="Task.position"
    )


class Task(IdMixin, TimestampMixin, Base):
    """A single item inside a plan.

    ``kind`` is one of: "main", "sub_goal", "gtm".
    ``org_id`` is denormalized from the parent plan for direct org-scoped queries.
    """

    __tablename__ = "tasks"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    why: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending"
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    plan: Mapped[Plan] = relationship(back_populates="tasks")


# ---------------------------------------------------------------------------
# AI Usage Log
# ---------------------------------------------------------------------------


class AICall(IdMixin, Base):
    """Metadata-only log of every AI agent invocation.

    Never stores prompt text or response text — only outcome metadata.
    """

    __tablename__ = "ai_calls"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    outcome: Mapped[str] = mapped_column(String(50), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
