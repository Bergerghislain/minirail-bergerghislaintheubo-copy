from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from minirail.orm import Base, UTCDateTime
from minirail.utils.date_utils import utc_now

if TYPE_CHECKING:
    from minirail.sales.models.booking import Booking


class BookingExpiryOutbox(Base):
    """Transactional outbox row for the delayed ``expire_booking`` actor.

    Written in the same TX as the PENDING booking. Published to remoulade
    *after* commit so a rolled-back create never enqueues, and a crash after
    commit still leaves a durable intent to publish.
    """

    __tablename__ = "booking_expiry_outbox"
    __table_args__ = (UniqueConstraint("booking_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("booking.id"))
    # Intended remoulade delay at schedule time (ms). Drain subtracts elapsed time.
    delay_ms: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    booking: Mapped[Booking] = relationship()
