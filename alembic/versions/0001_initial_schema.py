"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-08-10 14:38:19.907345

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "route",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_route")),
        sa.UniqueConstraint("code", name=op.f("uq_route_code")),
    )
    op.create_table(
        "sales_channel",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("api_key", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sales_channel")),
        sa.UniqueConstraint("api_key", name=op.f("uq_sales_channel_api_key")),
        sa.UniqueConstraint("name", name=op.f("uq_sales_channel_name")),
    )
    op.create_table(
        "station",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=5), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("timezone", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_station")),
        sa.UniqueConstraint("code", name=op.f("uq_station_code")),
    )
    op.create_table(
        "booking",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("booking_key", sa.String(), nullable=False),
        sa.Column("pnr", sa.String(length=6), nullable=False),
        sa.Column("sales_channel_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING", "CONFIRMED", "CANCELLED", "EXPIRED", name="bookingstatusenum", native_enum=False, length=20
            ),
            nullable=False,
        ),
        sa.Column("total_amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["sales_channel_id"], ["sales_channel.id"], name=op.f("fk_booking_sales_channel_id_sales_channel")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_booking")),
        sa.UniqueConstraint("booking_key", name=op.f("uq_booking_booking_key")),
        sa.UniqueConstraint("pnr", name=op.f("uq_booking_pnr")),
    )
    op.create_table(
        "service",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("route_id", sa.Integer(), nullable=False),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("train_number", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("SCHEDULED", "CANCELLED", name="servicestatusenum", native_enum=False, length=20),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["route_id"], ["route.id"], name=op.f("fk_service_route_id_route")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_service")),
        sa.UniqueConstraint("route_id", "service_date", "train_number", name=op.f("uq_service_route_id")),
    )
    op.create_table(
        "leg",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("origin_station_id", sa.Integer(), nullable=False),
        sa.Column("destination_station_id", sa.Integer(), nullable=False),
        sa.Column("departure_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("arrival_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seat_capacity", sa.Integer(), nullable=False),
        sa.Column("seats_booked", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["destination_station_id"], ["station.id"], name=op.f("fk_leg_destination_station_id_station")
        ),
        sa.ForeignKeyConstraint(["origin_station_id"], ["station.id"], name=op.f("fk_leg_origin_station_id_station")),
        sa.ForeignKeyConstraint(["service_id"], ["service.id"], name=op.f("fk_leg_service_id_service")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leg")),
        sa.UniqueConstraint("service_id", "rank", name=op.f("uq_leg_service_id")),
    )
    op.create_table(
        "od",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("origin_station_id", sa.Integer(), nullable=False),
        sa.Column("destination_station_id", sa.Integer(), nullable=False),
        sa.Column("first_leg_rank", sa.Integer(), nullable=False),
        sa.Column("last_leg_rank", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.ForeignKeyConstraint(
            ["destination_station_id"], ["station.id"], name=op.f("fk_od_destination_station_id_station")
        ),
        sa.ForeignKeyConstraint(["origin_station_id"], ["station.id"], name=op.f("fk_od_origin_station_id_station")),
        sa.ForeignKeyConstraint(["service_id"], ["service.id"], name=op.f("fk_od_service_id_service")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_od")),
        sa.UniqueConstraint("service_id", "origin_station_id", "destination_station_id", name=op.f("uq_od_service_id")),
    )
    op.create_table(
        "passenger",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("booking_id", sa.Integer(), nullable=False),
        sa.Column("first_name", sa.String(), nullable=False),
        sa.Column("last_name", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["booking_id"], ["booking.id"], name=op.f("fk_passenger_booking_id_booking")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_passenger")),
    )
    op.create_table(
        "ticket",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("booking_id", sa.Integer(), nullable=False),
        sa.Column("passenger_id", sa.Integer(), nullable=False),
        sa.Column("od_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("HELD", "CONFIRMED", "CANCELLED", "EXPIRED", name="ticketstatusenum", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column("price_at_sale", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.ForeignKeyConstraint(["booking_id"], ["booking.id"], name=op.f("fk_ticket_booking_id_booking")),
        sa.ForeignKeyConstraint(["od_id"], ["od.id"], name=op.f("fk_ticket_od_id_od")),
        sa.ForeignKeyConstraint(["passenger_id"], ["passenger.id"], name=op.f("fk_ticket_passenger_id_passenger")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket")),
        sa.UniqueConstraint("passenger_id", "od_id", name=op.f("uq_ticket_passenger_id")),
    )


def downgrade() -> None:
    op.drop_table("ticket")
    op.drop_table("passenger")
    op.drop_table("od")
    op.drop_table("leg")
    op.drop_table("service")
    op.drop_table("booking")
    op.drop_table("station")
    op.drop_table("sales_channel")
    op.drop_table("route")
