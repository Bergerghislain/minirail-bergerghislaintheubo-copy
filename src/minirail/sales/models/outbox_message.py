from datetime import datetime
from typing import Any

from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from minirail.orm import Base, UTCDateTime
from minirail.utils.date_utils import utc_now


class OutboxMessage(Base):
    """Transactional outbox: side-effect messages written in the same TX as
    the business row, published after commit.

    If the process dies between commit and publish, ``published_at`` stays
    NULL and a sweep (or the next publish call) delivers the message. That
    closes the window where a booking exists without its expiry message.
    """

    __tablename__ = "outbox_message"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_name: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    delay_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
