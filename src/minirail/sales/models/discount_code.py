from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from minirail.orm import Base, UTCDateTime
from minirail.utils.date_utils import utc_now

if TYPE_CHECKING:
    from minirail.sales.models.sales_channel import SalesChannel


class DiscountCode(Base):
    """A promotional code owned by a sales channel (partner).

    ``use_count`` is incremented when a booking is created with this code and
    must stay <= ``max_uses``. A PENDING booking that expires or is cancelled
    releases its use. Business logic for that lives outside this model.
    """

    __tablename__ = "discount_code"
    __table_args__ = (UniqueConstraint("sales_channel_id", "code", name="uq_discount_code_channel_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sales_channel_id: Mapped[int] = mapped_column(ForeignKey("sales_channel.id"))
    # Stored uppercase; clients may send any casing.
    code: Mapped[str] = mapped_column(String(32))
    # Percentage off the booking total, e.g. 10.00 = 10%.
    percent_off: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    max_uses: Mapped[int]
    use_count: Mapped[int] = mapped_column(default=0)
    # After this instant the code is no longer valid (checked by business logic).
    valid_until: Mapped[datetime | None] = mapped_column(UTCDateTime())
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    sales_channel: Mapped[SalesChannel] = relationship()
