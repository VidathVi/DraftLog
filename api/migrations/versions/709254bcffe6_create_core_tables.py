"""create_core_tables

Revision ID: 709254bcffe6
Revises: 9e87ebf2de15
Create Date: 2026-10-13 14:12:29.095180

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "709254bcffe6"
down_revision: str | Sequence[str] | None = "9e87ebf2de15"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. organizations
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    # 2. memberships
    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("org_role", sa.String(length=50), nullable=False, server_default="member"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "user_id", name="uq_memberships_org_user"),
    )
    op.create_index(op.f("ix_memberships_org_id"), "memberships", ["org_id"], unique=False)
    op.create_index(op.f("ix_memberships_user_id"), "memberships", ["user_id"], unique=False)

    # 3. invites
    op.create_table(
        "invites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("org_role", sa.String(length=50), nullable=False, server_default="member"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["memberships.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_invites_org_id"), "invites", ["org_id"], unique=False)

    # 4. teams
    op.create_table(
        "teams",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("lead_membership_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["lead_membership_id"], ["memberships.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_teams_org_id"), "teams", ["org_id"], unique=False)
    op.create_index(op.f("ix_teams_lead_membership_id"), "teams", ["lead_membership_id"], unique=False)

    # 5. team_members
    op.create_table(
        "team_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["membership_id"], ["memberships.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "membership_id", name="uq_team_members_team_membership"),
    )
    op.create_index(op.f("ix_team_members_team_id"), "team_members", ["team_id"], unique=False)
    op.create_index(op.f("ix_team_members_membership_id"), "team_members", ["membership_id"], unique=False)

    # 6. plans
    op.create_table(
        "plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("week_monday", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="draft"),
        sa.Column("lead_comment", sa.Text(), nullable=True),
        sa.Column("shipped", sa.Boolean(), nullable=False, server_default="false"),
        sa.ForeignKeyConstraint(["membership_id"], ["memberships.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("membership_id", "week_monday", name="uq_plans_membership_week"),
    )
    op.create_index(op.f("ix_plans_org_id"), "plans", ["org_id"], unique=False)
    op.create_index(op.f("ix_plans_membership_id"), "plans", ["membership_id"], unique=False)
    op.create_index(op.f("ix_plans_team_id"), "plans", ["team_id"], unique=False)

    # 7. tasks
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("why", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tasks_org_id"), "tasks", ["org_id"], unique=False)
    op.create_index(op.f("ix_tasks_plan_id"), "tasks", ["plan_id"], unique=False)

    # 8. ai_calls
    op.create_table(
        "ai_calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("outcome", sa.String(length=50), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_calls_created_at"), "ai_calls", ["created_at"], unique=False)
    op.create_index(op.f("ix_ai_calls_org_id"), "ai_calls", ["org_id"], unique=False)
    op.create_index(op.f("ix_ai_calls_user_id"), "ai_calls", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_table("ai_calls")
    op.drop_table("tasks")
    op.drop_table("plans")
    op.drop_table("team_members")
    op.drop_table("teams")
    op.drop_table("invites")
    op.drop_table("memberships")
    op.drop_table("organizations")
