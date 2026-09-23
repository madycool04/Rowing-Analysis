"""Add coach roles, assignments, and workout comments.

Revision ID: 20260923_01
Revises: None
"""
from alembic import op
import sqlalchemy as sa

revision = "20260923_01"
down_revision = None
branch_labels = None
depends_on = None


def _columns(inspector, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    # A new installation has no legacy schema to alter. Create the complete
    # current model set, while existing deployments receive additive changes.
    if "users" not in tables:
        from app.db.base import Base
        from app.db.session import import_all_models

        import_all_models()
        Base.metadata.create_all(bind=bind)
        return

    user_columns = _columns(inspector, "users")
    if "role" not in user_columns:
        op.add_column(
            "users",
            sa.Column("role", sa.String(length=20), nullable=False, server_default="athlete"),
        )
    if "display_name" not in user_columns:
        op.add_column("users", sa.Column("display_name", sa.String(length=255), nullable=True))

    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "coach_athlete_assignments" not in tables:
        op.create_table(
            "coach_athlete_assignments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("coach_id", sa.Integer(), nullable=False),
            sa.Column("athlete_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["coach_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["athlete_id"], ["athletes.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("coach_id", "athlete_id", name="uq_coach_athlete_assignment"),
        )
        op.create_index("ix_coach_athlete_assignments_coach_id", "coach_athlete_assignments", ["coach_id"])
        op.create_index("ix_coach_athlete_assignments_athlete_id", "coach_athlete_assignments", ["athlete_id"])

    if "workout_comments" not in tables:
        op.create_table(
            "workout_comments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("workout_id", sa.Integer(), nullable=False),
            sa.Column("coach_id", sa.Integer(), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("coach_name_snapshot", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["workout_id"], ["workouts.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["coach_id"], ["users.id"], ondelete="RESTRICT"),
        )
        op.create_index("ix_workout_comments_workout_id", "workout_comments", ["workout_id"])
        op.create_index("ix_workout_comments_coach_id", "workout_comments", ["coach_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "workout_comments" in tables:
        op.drop_table("workout_comments")
    if "coach_athlete_assignments" in tables:
        op.drop_table("coach_athlete_assignments")
    inspector = sa.inspect(bind)
    if "users" in inspector.get_table_names():
        columns = _columns(inspector, "users")
        if "display_name" in columns:
            op.drop_column("users", "display_name")
        if "role" in columns:
            op.drop_column("users", "role")
