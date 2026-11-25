"""discount code and booking min_price

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-25 13:30:00.000000

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
        sa.Column("percent_off", sa.Integer(), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("use_count", sa.Integer(), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["sales_channel_id"],
            ["sales_channel.id"],
            name=op.f("fk_discount_code_sales_channel_id_sales_channel"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discount_code")),
        sa.UniqueConstraint("sales_channel_id", "code", name=op.f("uq_discount_code_sales_channel_id")),
    )
    op.add_column("booking", sa.Column("min_price", sa.Numeric(precision=10, scale=2), nullable=True))


def downgrade() -> None:
    op.drop_column("booking", "min_price")
    op.drop_table("discount_code")
