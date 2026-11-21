from dataclasses import dataclass
from typing import ClassVar, override

from minirail.orm import MinirailSession
from minirail.sales.models import Booking, BookingStatusEnum, TicketStatusEnum
from minirail.sales.service.booking import get_booking_by_key
from minirail.utils import payments
from minirail.utils.date_utils import utc_now
from minirail.utils.exc import BookingNotPendingException, ItemNotFoundException, PaymentDeclinedException
from minirail.utils.job import BaseJob


@dataclass(kw_only=True)
class ConfirmBookingJob(BaseJob[Booking]):
    """Charge the customer and confirm the booking (seats become sold)."""

    business_exceptions: ClassVar = (ItemNotFoundException, BookingNotPendingException, PaymentDeclinedException)

    session: MinirailSession
    booking_key: str
    payment_token: str

    @override
    def _call(self) -> None:
        booking = get_booking_by_key(self.session, self.booking_key)
        if booking is None:
            raise ItemNotFoundException(f"Booking {self.booking_key!r} not found")
        if booking.status is not BookingStatusEnum.PENDING:
            raise BookingNotPendingException(f"Booking is {booking.status}, only PENDING bookings can be confirmed")
        if booking.expires_at is not None and booking.expires_at <= utc_now():
            # The expiry actor will (or already did) release the seats.
            raise BookingNotPendingException("The booking hold has expired")

        result = payments.charge(self.payment_token, booking.total_amount, booking.currency)
        if not result.success:
            raise PaymentDeclinedException(f"Payment declined ({result.failure_reason})")

        booking.status = BookingStatusEnum.CONFIRMED
        booking.confirmed_at = utc_now()
        booking.expires_at = None
        for ticket in booking.tickets:
            ticket.status = TicketStatusEnum.CONFIRMED
        self.session.flush()
        self.set_output(booking)
