from dataclasses import dataclass
from typing import ClassVar, override

from minirail.orm import MinirailSession
from minirail.sales.models import Booking, BookingStatusEnum, TicketStatusEnum
from minirail.sales.service.booking import get_booking_by_key, release_seats_for_booking
from minirail.sales.service.discount_code import release_discount_use
from minirail.utils.exc import BookingNotPendingException, ItemNotFoundException
from minirail.utils.job import BaseJob

CANCELLABLE_STATUSES = (BookingStatusEnum.PENDING, BookingStatusEnum.CONFIRMED)


@dataclass(kw_only=True)
class CancelBookingJob(BaseJob[Booking]):
    """Cancel a PENDING or CONFIRMED booking and give its seats back.

    A discount use reserved at creation is released only when the booking was
    still PENDING (never paid). A confirmed-then-cancelled booking keeps the
    use consumed — the partner promotion was already applied to a paid sale.
    """

    business_exceptions: ClassVar = (ItemNotFoundException, BookingNotPendingException)

    session: MinirailSession
    booking_key: str

    @override
    def _call(self) -> None:
        booking = get_booking_by_key(self.session, self.booking_key)
        if booking is None:
            raise ItemNotFoundException(f"Booking {self.booking_key!r} not found")
        if booking.status not in CANCELLABLE_STATUSES:
            raise BookingNotPendingException(f"Booking is {booking.status} and cannot be cancelled")

        was_pending = booking.status is BookingStatusEnum.PENDING
        booking.status = BookingStatusEnum.CANCELLED
        booking.expires_at = None
        for ticket in booking.tickets:
            ticket.status = TicketStatusEnum.CANCELLED
        release_seats_for_booking(self.session, booking)
        if was_pending and booking.discount_code is not None:
            release_discount_use(self.session, booking.discount_code)
        self.session.flush()
        self.set_output(booking)
