"""discount redemption journal and discount_code checks

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-25 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_discount_code_percent_off",
        "discount_code",
        "percent_off >= 1 AND percent_off <= 100",
    )
    op.create_check_constraint("ck_discount_code_max_uses", "discount_code", "max_uses >= 1")
    op.create_check_constraint(
        "ck_discount_code_use_count",
        "discount_code",
        "use_count >= 0 AND use_count <= max_uses",
    )
    op.create_check_constraint("ck_discount_code_code_uppercase", "discount_code", "code = upper(code)")

    op.create_table(
        "discount_redemption",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("discount_code_id", sa.Integer(), nullable=False),
        sa.Column("booking_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "RESERVED",
                "RELEASED",
                "CONSUMED",
                name="discountredemptionstatusenum",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["booking_id"],
            ["booking.id"],
            name=op.f("fk_discount_redemption_booking_id_booking"),
        ),
        sa.ForeignKeyConstraint(
            ["discount_code_id"],
            ["discount_code.id"],
            name=op.f("fk_discount_redemption_discount_code_id_discount_code"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discount_redemption")),
        sa.UniqueConstraint("booking_id", name=op.f("uq_discount_redemption_booking_id")),
    )


def downgrade() -> None:
    op.drop_table("discount_redemption")
    op.drop_constraint("ck_discount_code_code_uppercase", "discount_code", type_="check")
    op.drop_constraint("ck_discount_code_use_count", "discount_code", type_="check")
    op.drop_constraint("ck_discount_code_max_uses", "discount_code", type_="check")
    op.drop_constraint("ck_discount_code_percent_off", "discount_code", type_="check")
