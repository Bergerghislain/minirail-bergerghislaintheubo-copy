from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from minirail.orm import Base, UTCDateTime
from minirail.utils.date_utils import utc_now


class IdempotencyKey(Base):
    """Client-supplied key that makes booking creation replay-safe.

    Scoped per sales channel: the same key from two partners is two intents.
    ``request_hash`` detects a key reused with a different body (conflict).
    """

    __tablename__ = "idempotency_key"
    __table_args__ = (UniqueConstraint("sales_channel_id", "key", name="uq_idempotency_key_channel_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sales_channel_id: Mapped[int] = mapped_column(ForeignKey("sales_channel.id"), index=True)
    key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    booking_key: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
