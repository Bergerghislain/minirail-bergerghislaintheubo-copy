from dataclasses import dataclass
from typing import ClassVar, override

from minirail.orm import MinirailSession
from minirail.sales.models import Booking, BookingStatusEnum, TicketStatusEnum
from minirail.sales.service.booking import get_booking_by_key
from minirail.sales.service.discount_code import consume_discount_redemption
from minirail.utils.date_utils import utc_now
from minirail.utils.exc import BookingNotPendingException, ItemNotFoundException
from minirail.utils.job import BaseJob


@dataclass(kw_only=True)
class ClaimConfirmBookingJob(BaseJob[Booking]):
    """Mark a PENDING booking as CONFIRMING so payment can run outside the TX.

    Holding row locks across a PSP round-trip would stall concurrent work on
    the same seats/code. Claim first, charge outside, then finalize or abort.
    """

    business_exceptions: ClassVar = (ItemNotFoundException, BookingNotPendingException)

    session: MinirailSession
    booking_key: str

    @override
    def _call(self) -> None:
        booking = get_booking_by_key(self.session, self.booking_key)
        if booking is None:
            raise ItemNotFoundException(f"Booking {self.booking_key!r} not found")
        if booking.status is not BookingStatusEnum.PENDING:
            raise BookingNotPendingException(f"Booking is {booking.status}, only PENDING bookings can be confirmed")
        if booking.expires_at is not None and booking.expires_at <= utc_now():
            raise BookingNotPendingException("The booking hold has expired")

        booking.status = BookingStatusEnum.CONFIRMING
        self.session.flush()
        self.set_output(booking)


@dataclass(kw_only=True)
class FinalizeConfirmBookingJob(BaseJob[Booking]):
    """Complete confirmation after a successful charge outside the transaction."""

    business_exceptions: ClassVar = (ItemNotFoundException, BookingNotPendingException)

    session: MinirailSession
    booking_key: str

    @override
    def _call(self) -> None:
        booking = get_booking_by_key(self.session, self.booking_key)
        if booking is None:
            raise ItemNotFoundException(f"Booking {self.booking_key!r} not found")
        if booking.status is not BookingStatusEnum.CONFIRMING:
            raise BookingNotPendingException(f"Booking is {booking.status}, expected CONFIRMING")

        booking.status = BookingStatusEnum.CONFIRMED
        booking.confirmed_at = utc_now()
        booking.expires_at = None
        for ticket in booking.tickets:
            ticket.status = TicketStatusEnum.CONFIRMED
        consume_discount_redemption(self.session, booking)
        self.session.flush()
        self.set_output(booking)


@dataclass(kw_only=True)
class AbortConfirmBookingJob(BaseJob[Booking]):
    """Return a CONFIRMING booking to PENDING after a declined payment."""

    business_exceptions: ClassVar = (ItemNotFoundException, BookingNotPendingException)

    session: MinirailSession
    booking_key: str

    @override
    def _call(self) -> None:
        booking = get_booking_by_key(self.session, self.booking_key)
        if booking is None:
            raise ItemNotFoundException(f"Booking {self.booking_key!r} not found")
        if booking.status is not BookingStatusEnum.CONFIRMING:
            raise BookingNotPendingException(f"Booking is {booking.status}, expected CONFIRMING")

        booking.status = BookingStatusEnum.PENDING
        self.session.flush()
        self.set_output(booking)
