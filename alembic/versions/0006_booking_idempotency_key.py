"""booking idempotency key

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-25 14:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "booking_idempotency_key",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sales_channel_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("booking_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["booking_id"],
            ["booking.id"],
            name=op.f("fk_booking_idempotency_key_booking_id_booking"),
        ),
        sa.ForeignKeyConstraint(
            ["sales_channel_id"],
            ["sales_channel.id"],
            name=op.f("fk_booking_idempotency_key_sales_channel_id_sales_channel"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_booking_idempotency_key")),
        sa.UniqueConstraint("sales_channel_id", "key", name=op.f("uq_booking_idempotency_key_sales_channel_id")),
    )


def downgrade() -> None:
    op.drop_table("booking_idempotency_key")
