from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from minirail.orm import Base, UTCDateTime
from minirail.utils.date_utils import utc_now

if TYPE_CHECKING:
    from minirail.sales.models.booking import Booking
    from minirail.sales.models.sales_channel import SalesChannel


class BookingIdempotencyKey(Base):
    """Optional client Idempotency-Key for POST /api/bookings/, scoped per channel.

    Same key + same request fingerprint → replay the stored booking.
    Same key + different fingerprint → conflict.
    """

    __tablename__ = "booking_idempotency_key"
    __table_args__ = (UniqueConstraint("sales_channel_id", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sales_channel_id: Mapped[int] = mapped_column(ForeignKey("sales_channel.id"))
    key: Mapped[str] = mapped_column(String(255))
    # SHA-256 hex of the canonical create payload.
    request_hash: Mapped[str] = mapped_column(String(64))
    booking_id: Mapped[int] = mapped_column(ForeignKey("booking.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    sales_channel: Mapped[SalesChannel] = relationship()
    booking: Mapped[Booking] = relationship()
