"""booking expiry outbox

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-25 14:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "booking_expiry_outbox",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("booking_id", sa.Integer(), nullable=False),
        sa.Column("delay_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["booking_id"],
            ["booking.id"],
            name=op.f("fk_booking_expiry_outbox_booking_id_booking"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_booking_expiry_outbox")),
        sa.UniqueConstraint("booking_id", name=op.f("uq_booking_expiry_outbox_booking_id")),
    )


def downgrade() -> None:
    op.drop_table("booking_expiry_outbox")
