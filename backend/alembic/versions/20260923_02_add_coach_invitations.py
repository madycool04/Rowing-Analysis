"""Add consent-based coach-athlete invitations.

Revision ID: 20260923_02
Revises: 20260923_01
"""
from alembic import op
import sqlalchemy as sa

revision = "20260923_02"
down_revision = "20260923_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "coach_athlete_invitations" in inspector.get_table_names():
        return
    op.create_table(
        "coach_athlete_invitations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("coach_id", sa.Integer(), nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["coach_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["athlete_id"], ["athletes.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("coach_id", "athlete_id", name="uq_coach_athlete_invitation"),
    )
    op.create_index("ix_coach_athlete_invitations_coach_id", "coach_athlete_invitations", ["coach_id"])
    op.create_index("ix_coach_athlete_invitations_athlete_id", "coach_athlete_invitations", ["athlete_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "coach_athlete_invitations" in inspector.get_table_names():
        op.drop_table("coach_athlete_invitations")
