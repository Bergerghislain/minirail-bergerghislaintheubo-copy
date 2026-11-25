from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from minirail.orm import Base, UTCDateTime
from minirail.utils.date_utils import utc_now

if TYPE_CHECKING:
    from minirail.sales.models.sales_channel import SalesChannel


class DiscountCode(Base):
    """A percent-off promo code owned by one sales channel (partner).

    Uniqueness is per channel: the same string may exist on two partners.
    Codes are stored uppercase (same convention as station/route codes) so
    lookups are case-insensitive without a functional index.
    """

    __tablename__ = "discount_code"
    __table_args__ = (
        UniqueConstraint("sales_channel_id", "code"),
        CheckConstraint("percent_off >= 1 AND percent_off <= 100", name="percent_off"),
        CheckConstraint("max_uses >= 1", name="max_uses"),
        CheckConstraint("use_count >= 0 AND use_count <= max_uses", name="use_count"),
        CheckConstraint("code = upper(code)", name="code_uppercase"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sales_channel_id: Mapped[int] = mapped_column(ForeignKey("sales_channel.id"))
    # Stored uppercase, e.g. "SAVE10".
    code: Mapped[str] = mapped_column(String(32))
    # Whole percent points: 10 means 10% off. Not a fraction.
    percent_off: Mapped[int]
    max_uses: Mapped[int]
    use_count: Mapped[int] = mapped_column(default=0)
    # Soft expiry; None means no end date. Compared in UTC.
    valid_until: Mapped[datetime | None] = mapped_column(UTCDateTime())
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    sales_channel: Mapped[SalesChannel] = relationship()
