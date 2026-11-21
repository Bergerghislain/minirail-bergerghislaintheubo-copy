"""discount codes

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-21 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "discount_code",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sales_channel_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("percent_off", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("use_count", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["sales_channel_id"],
            ["sales_channel.id"],
            name=op.f("fk_discount_code_sales_channel_id_sales_channel"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discount_code")),
        sa.UniqueConstraint("sales_channel_id", "code", name="uq_discount_code_channel_code"),
    )
    op.add_column("booking", sa.Column("discount_code_id", sa.Integer(), nullable=True))
    op.add_column(
        "booking",
        sa.Column("discount_amount", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0.00"),
    )
    op.create_foreign_key(
        op.f("fk_booking_discount_code_id_discount_code"),
        "booking",
        "discount_code",
        ["discount_code_id"],
        ["id"],
    )
    # server_default was only needed to backfill existing rows; drop it so the
    # ORM default is the single source of truth going forward.
    op.alter_column("booking", "discount_amount", server_default=None)


def downgrade() -> None:
    op.drop_constraint(op.f("fk_booking_discount_code_id_discount_code"), "booking", type_="foreignkey")
    op.drop_column("booking", "discount_amount")
    op.drop_column("booking", "discount_code_id")
    op.drop_table("discount_code")
