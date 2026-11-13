"""Store bookings with a global, immediate overlap guarantee."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ExcludeConstraint

revision: str = "0003_bookings"
down_revision: str | None = "0002_event_types"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "bookings",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("event_type_id", sa.String(64), sa.ForeignKey("event_types.id"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("guest_name", sa.String(120), nullable=False),
        sa.Column("guest_email", sa.String(254), nullable=False),
        sa.Column("guest_comment", sa.String(2000), nullable=False),
        sa.CheckConstraint("starts_at < ends_at", name="ck_booking_positive_interval"),
        sa.CheckConstraint("isfinite(starts_at) AND isfinite(ends_at)", name="ck_booking_finite"),
        ExcludeConstraint(
            (sa.text("tstzrange(starts_at, ends_at, '[)')"), "&&"),
            name="ex_bookings_overlap",
            using="gist",
        ),
    )


def downgrade() -> None:
    op.drop_table("bookings")
