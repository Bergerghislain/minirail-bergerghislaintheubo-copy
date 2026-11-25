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

    Lifecycle: PENDING (seats held, awaiting payment) → CONFIRMED, or
    → EXPIRED (payment never came, seats released by the expiry actor), or
    → CANCELLED (explicitly cancelled, seats released).
    """

    __tablename__ = "booking"
    __table_args__ = (
        # The expiry sweep scans for PENDING bookings past their expires_at;
        # without this index that query degrades linearly with table size.
        Index("ix_booking_status_expires_at", "status", "expires_at"),
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
    # Company-wide floor below which a discount must not apply. Lives on the
    # booking (not DiscountCode): the threshold is a global config value that
    # will be copied onto each booking at sale time so a later config change
    # cannot rewrite the rule that was applied to this sale — same idea as
    # Ticket.price_at_sale. Null on bookings created before that snapshotting
    # existed, or when no threshold was in force.
    min_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    # Optional promo applied at creation. Discount lives on the booking total
    # only — ticket.price_at_sale stays the OD list price.
    discount_code_id: Mapped[int | None] = mapped_column(ForeignKey("discount_code.id"))
    discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    # While PENDING: the moment the expiry actor may release the held seats.
    # Cleared on confirmation.
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    sales_channel: Mapped[SalesChannel] = relationship()
    applied_discount: Mapped[DiscountCode | None] = relationship()
    passengers: Mapped[list[Passenger]] = relationship(back_populates="booking")
    tickets: Mapped[list[Ticket]] = relationship(back_populates="booking")

    @property
    def discount_code(self) -> str | None:
        """Public code string for API output (None when no promo was applied)."""
        return None if self.applied_discount is None else self.applied_discount.code
