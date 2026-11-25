from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from minirail.orm import Base, UTCDateTime
from minirail.utils.date_utils import utc_now

if TYPE_CHECKING:
    from minirail.sales.models.booking import Booking
    from minirail.sales.models.discount_code import DiscountCode


class DiscountRedemptionStatusEnum(StrEnum):
    """Lifecycle of one booking's claim on a discount code.

    RESERVED — PENDING/CONFIRMING booking holds a use.
    RELEASED — the hold was given back (cancel/expire before payment).
    CONSUMED — the booking was confirmed; the use stays spent.
    """

    RESERVED = "RESERVED"
    RELEASED = "RELEASED"
    CONSUMED = "CONSUMED"


class DiscountRedemption(Base):
    """Audit journal of who used a code, when, and what happened to that use.

    ``DiscountCode.use_count`` stays as a denormalized counter of non-RELEASED
    rows so the hot ``max_uses`` check does not recount the journal. The journal
    is the source of truth for reconstruction and forensics.
    """

    __tablename__ = "discount_redemption"
    __table_args__ = (UniqueConstraint("booking_id", name="uq_discount_redemption_booking_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    discount_code_id: Mapped[int] = mapped_column(ForeignKey("discount_code.id"), index=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("booking.id"))
    status: Mapped[DiscountRedemptionStatusEnum] = mapped_column(
        Enum(DiscountRedemptionStatusEnum, native_enum=False, length=20),
        default=DiscountRedemptionStatusEnum.RESERVED,
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    released_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    discount_code: Mapped[DiscountCode] = relationship()
    booking: Mapped[Booking] = relationship()
