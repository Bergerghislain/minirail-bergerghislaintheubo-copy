"""discount hardening: checks, journal, outbox, idempotency

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-25 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # op.f() marks names as already convention-expanded so MetaData does not
    # apply ck_%(table_name)s_%(constraint_name)s a second time.
    op.create_check_constraint(
        op.f("ck_discount_code_percent_off_range"),
        "discount_code",
        "percent_off > 0 AND percent_off <= 100",
    )
    op.create_check_constraint(
        op.f("ck_discount_code_max_uses_positive"),
        "discount_code",
        "max_uses >= 1",
    )
    op.create_check_constraint(
        op.f("ck_discount_code_use_count_non_negative"),
        "discount_code",
        "use_count >= 0",
    )
    op.create_check_constraint(
        op.f("ck_discount_code_use_count_within_max"),
        "discount_code",
        "use_count <= max_uses",
    )
    op.create_check_constraint(
        op.f("ck_discount_code_code_uppercase"),
        "discount_code",
        "code = upper(code)",
    )

    op.create_index("ix_booking_discount_code_id", "booking", ["discount_code_id"], unique=False)

    # native_enum=False → VARCHAR; expand the allowed labels for CONFIRMING.
    op.alter_column(
        "booking",
        "status",
        existing_type=sa.Enum(
            "PENDING",
            "CONFIRMED",
            "CANCELLED",
            "EXPIRED",
            name="bookingstatusenum",
            native_enum=False,
            length=20,
        ),
        type_=sa.Enum(
            "PENDING",
            "CONFIRMING",
            "CONFIRMED",
            "CANCELLED",
            "EXPIRED",
            name="bookingstatusenum",
            native_enum=False,
            length=20,
        ),
        existing_nullable=False,
    )

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
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("booking_id", name="uq_discount_redemption_booking_id"),
    )
    op.create_index(
        op.f("ix_discount_redemption_discount_code_id"),
        "discount_redemption",
        ["discount_code_id"],
        unique=False,
    )

    op.create_table(
        "outbox_message",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("actor_name", sa.String(length=100), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("delay_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_message")),
    )

    op.create_table(
        "idempotency_key",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sales_channel_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("booking_key", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["sales_channel_id"],
            ["sales_channel.id"],
            name=op.f("fk_idempotency_key_sales_channel_id_sales_channel"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_idempotency_key")),
        sa.UniqueConstraint("sales_channel_id", "key", name="uq_idempotency_key_channel_key"),
    )
    op.create_index(
        op.f("ix_idempotency_key_sales_channel_id"),
        "idempotency_key",
        ["sales_channel_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_idempotency_key_sales_channel_id"), table_name="idempotency_key")
    op.drop_table("idempotency_key")
    op.drop_table("outbox_message")
    op.drop_index(op.f("ix_discount_redemption_discount_code_id"), table_name="discount_redemption")
    op.drop_table("discount_redemption")
    op.alter_column(
        "booking",
        "status",
        existing_type=sa.Enum(
            "PENDING",
            "CONFIRMING",
            "CONFIRMED",
            "CANCELLED",
            "EXPIRED",
            name="bookingstatusenum",
            native_enum=False,
            length=20,
        ),
        type_=sa.Enum(
            "PENDING",
            "CONFIRMED",
            "CANCELLED",
            "EXPIRED",
            name="bookingstatusenum",
            native_enum=False,
            length=20,
        ),
        existing_nullable=False,
    )
    op.drop_index("ix_booking_discount_code_id", table_name="booking")
    op.drop_constraint(op.f("ck_discount_code_code_uppercase"), "discount_code", type_="check")
    op.drop_constraint(op.f("ck_discount_code_use_count_within_max"), "discount_code", type_="check")
    op.drop_constraint(op.f("ck_discount_code_use_count_non_negative"), "discount_code", type_="check")
    op.drop_constraint(op.f("ck_discount_code_max_uses_positive"), "discount_code", type_="check")
    op.drop_constraint(op.f("ck_discount_code_percent_off_range"), "discount_code", type_="check")
