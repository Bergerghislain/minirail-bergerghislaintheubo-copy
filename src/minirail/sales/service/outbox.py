"""Transactional outbox for booking expiry messages.

``schedule_*`` flushes only (same TX as the booking). ``drain_*`` publishes to
remoulade and marks rows published — still flush-only; the caller commits.
"""

from sqlalchemy import select

from minirail.orm import MinirailSession
from minirail.sales.models import BookingExpiryOutbox
from minirail.utils.date_utils import utc_now


def schedule_booking_expiry(session: MinirailSession, *, booking_id: int, delay_ms: int) -> BookingExpiryOutbox:
    """Record intent to enqueue ``expire_booking`` for ``booking_id`` after ``delay_ms``."""
    row = BookingExpiryOutbox(booking_id=booking_id, delay_ms=delay_ms)
    session.add(row)
    session.flush()
    return row


def drain_booking_expiry_outbox(session: MinirailSession, *, limit: int = 100) -> int:
    """Publish unpublished expiry outbox rows to remoulade; mark them published.

    Remaining delay accounts for time spent sitting in the outbox so a late
    drain does not push expiry further out. Returns the number of rows published.

    Limit without a periodic drain: a process crash between the booking commit
    and this drain leaves rows unpublished until something calls drain again
    (e.g. the next successful create, or a future worker). ``expire-stale-bookings``
    still recovers seats, but the delayed actor path for those rows is idle.
    """
    # Imported lazily so models/service import stays free of remoulade at module load
    # for environments that only write the outbox.
    from minirail.sales.actors.booking_expiry import expire_booking

    statement = (
        select(BookingExpiryOutbox)
        .where(BookingExpiryOutbox.published_at.is_(None))
        .order_by(BookingExpiryOutbox.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    rows = list(session.scalars(statement).all())
    now = utc_now()
    for row in rows:
        elapsed_ms = int((now - row.created_at).total_seconds() * 1000)
        remaining_delay = max(0, row.delay_ms - elapsed_ms)
        expire_booking.send_with_options(args=(row.booking_id,), delay=remaining_delay)
        row.published_at = now
    session.flush()
    return len(rows)
