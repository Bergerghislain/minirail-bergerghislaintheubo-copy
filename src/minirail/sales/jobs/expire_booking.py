from dataclasses import dataclass
from typing import override

from sqlalchemy import select

from minirail.orm import MinirailSession
from minirail.sales.models import Booking, BookingStatusEnum, TicketStatusEnum
from minirail.sales.service.booking import get_booking_by_id, release_seats_for_booking
from minirail.sales.service.discount_code import release_discount_use
from minirail.utils.date_utils import utc_now
from minirail.utils.job import BaseJob


@dataclass(kw_only=True)
class ExpireBookingJob(BaseJob[bool]):
    """Release a PENDING booking whose payment never came. Output: whether it expired.

    The expiry message is scheduled at booking creation and fires
    unconditionally — including for bookings that were confirmed or cancelled
    in the meantime, and possibly more than once if a message is redelivered.
    The job therefore checks the status first and leaves anything that is no
    longer PENDING untouched.

    Any discount use reserved at creation is released with the seats.
    """

    session: MinirailSession
    booking_id: int

    @override
    def _call(self) -> None:
        booking = get_booking_by_id(self.session, self.booking_id)
        if booking is None or booking.status is not BookingStatusEnum.PENDING:
            self.set_output(False)
            return
        if booking.expires_at is not None and booking.expires_at > utc_now():
            # Not due yet (e.g. the manual sweep raced a fresh booking).
            self.set_output(False)
            return

        booking.status = BookingStatusEnum.EXPIRED
        booking.expires_at = None
        for ticket in booking.tickets:
            ticket.status = TicketStatusEnum.EXPIRED
        release_seats_for_booking(self.session, booking)
        if booking.discount_code is not None:
            release_discount_use(self.session, booking.discount_code)
        self.session.flush()
        self.set_output(True)


def find_stale_booking_ids(session: MinirailSession) -> list[int]:
    """PENDING bookings past their expiry — the ops fallback sweep
    (`minirail expire-stale-bookings`) when delayed messages were lost.
    Served by the (status, expires_at) index."""
    statement = select(Booking.id).where(
        Booking.status == BookingStatusEnum.PENDING,
        Booking.expires_at <= utc_now(),
    )
    return list(session.scalars(statement).all())
