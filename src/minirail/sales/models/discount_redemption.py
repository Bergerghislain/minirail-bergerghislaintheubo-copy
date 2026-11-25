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
    """Journal lifecycle for one booking's claim on a discount use.

    RESERVED at PENDING create → RELEASED (unpaid cancel/expire) or CONSUMED (confirm).
    """

    RESERVED = "RESERVED"
    RELEASED = "RELEASED"
    CONSUMED = "CONSUMED"


class DiscountRedemption(Base):
    """Append-only-ish journal row: one redemption attempt per discounted booking.

    Status transitions are applied with atomic UPDATEs (RESERVED → RELEASED|CONSUMED)
    so concurrent cancel/expire cannot double-release a use.
    """

    __tablename__ = "discount_redemption"
    __table_args__ = (UniqueConstraint("booking_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    discount_code_id: Mapped[int] = mapped_column(ForeignKey("discount_code.id"))
    booking_id: Mapped[int] = mapped_column(ForeignKey("booking.id"))
    status: Mapped[DiscountRedemptionStatusEnum] = mapped_column(
        Enum(DiscountRedemptionStatusEnum, native_enum=False, length=20),
        default=DiscountRedemptionStatusEnum.RESERVED,
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    discount_code: Mapped[DiscountCode] = relationship()
    booking: Mapped[Booking] = relationship()
