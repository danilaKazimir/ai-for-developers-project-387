"""Create the organizer's shared calendar and event types."""

import sqlalchemy as sa
from alembic import op

revision: str = "0002_event_types"
down_revision: str | None = "0001_baseline"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    calendar = op.create_table(
        "calendars",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_single_calendar"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.bulk_insert(calendar, [{"id": 1, "timezone": "Europe/Moscow"}])
    op.create_table(
        "event_types",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(2000), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.CheckConstraint("id ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="ck_event_type_id"),
        sa.CheckConstraint("char_length(id) BETWEEN 1 AND 64", name="ck_event_type_id_length"),
        sa.CheckConstraint("char_length(btrim(name)) BETWEEN 1 AND 120", name="ck_event_type_name"),
        sa.CheckConstraint("char_length(description) <= 2000", name="ck_event_type_description"),
        sa.CheckConstraint("duration_minutes BETWEEN 1 AND 540", name="ck_event_type_duration"),
        sa.PrimaryKeyConstraint("id", name="event_types_pkey"),
    )


def downgrade() -> None:
    op.drop_table("event_types")
    op.drop_table("calendars")
