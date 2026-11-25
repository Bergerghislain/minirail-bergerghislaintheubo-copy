"""booking discount fields

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-25 13:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("booking", sa.Column("discount_code_id", sa.Integer(), nullable=True))
    op.add_column("booking", sa.Column("discount_amount", sa.Numeric(precision=10, scale=2), nullable=True))
    op.create_foreign_key(
        op.f("fk_booking_discount_code_id_discount_code"),
        "booking",
        "discount_code",
        ["discount_code_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_booking_discount_code_id_discount_code"), "booking", type_="foreignkey")
    op.drop_column("booking", "discount_amount")
    op.drop_column("booking", "discount_code_id")
