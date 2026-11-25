import secrets
import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from minirail.orm import Base, UTCDateTime
from minirail.utils.date_utils import utc_now

if TYPE_CHECKING:
    from minirail.sales.models.discount_code import DiscountCode
    from minirail.sales.models.passenger import Passenger
    from minirail.sales.models.sales_channel import SalesChannel
    from minirail.sales.models.ticket import Ticket


class BookingStatusEnum(StrEnum):
    PENDING = "PENDING"
    # Claimed for payment: the PSP call runs outside any DB transaction so a
    # slow partner cannot hold row locks. Finalize or abort after the charge.
    CONFIRMING = "CONFIRMING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


def generate_booking_key() -> str:
    return uuid.uuid4().hex


# No 0/O/1/I: PNRs are read over the phone.
_PNR_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_pnr() -> str:
    # Uniqueness is enforced by the database; at this demo's scale a
    # collision is astronomically unlikely, so there is no retry loop.
    return "".join(secrets.choice(_PNR_ALPHABET) for _ in range(6))


class Booking(Base):
    """An order placed by a sales channel: passengers + tickets + payment state.

    Lifecycle: PENDING (seats held, awaiting payment) → CONFIRMING (payment in
    flight) → CONFIRMED, or → EXPIRED (payment never came, seats released by
    the expiry actor), or → CANCELLED (explicitly cancelled, seats released).
    """

    __tablename__ = "booking"
    __table_args__ = (
        # The expiry sweep scans for PENDING bookings past their expires_at;
        # without this index that query degrades linearly with table size.
        Index("ix_booking_status_expires_at", "status", "expires_at"),
        # PostgreSQL does not index FK columns automatically; reporting by
        # promotion and joining redemptions need this.
        Index("ix_booking_discount_code_id", "discount_code_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Internal identifier used in API paths.
    booking_key: Mapped[str] = mapped_column(unique=True, default=generate_booking_key)
    # Short customer-facing reference, printed on tickets.
    pnr: Mapped[str] = mapped_column(String(6), unique=True, default=generate_pnr)
    sales_channel_id: Mapped[int] = mapped_column(ForeignKey("sales_channel.id"))
    status: Mapped[BookingStatusEnum] = mapped_column(
        Enum(BookingStatusEnum, native_enum=False, length=20),
        default=BookingStatusEnum.PENDING,
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    # Optional promotion applied at creation time.
    discount_code_id: Mapped[int | None] = mapped_column(ForeignKey("discount_code.id"))
    # How much was subtracted from the full OD price (0 when no code).
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    # Booking total must be at least this amount for a discount code to apply.
    # Same threshold for every booking (centralized here, not on DiscountCode).
    min_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    # While PENDING: the moment the expiry actor may release the held seats.
    # Cleared on confirmation.
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    sales_channel: Mapped[SalesChannel] = relationship()
    discount_code: Mapped[DiscountCode | None] = relationship()
    passengers: Mapped[list[Passenger]] = relationship(back_populates="booking")
    tickets: Mapped[list[Ticket]] = relationship(back_populates="booking")
