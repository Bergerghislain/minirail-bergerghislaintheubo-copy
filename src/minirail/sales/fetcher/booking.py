from typing import override

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from minirail.sales.models import Booking
from minirail.sales.schemas.booking import BookingOutputSchema
from minirail.utils.fetcher import SQLOneFetcher


class BookingFetcher(SQLOneFetcher[BookingOutputSchema]):
    """Booking read model. Not cached: bookings change status and money is
    involved — always serve the committed truth."""

    @property
    @override
    def output_schema(self) -> type[BookingOutputSchema]:
        return BookingOutputSchema

    @override
    def _fetch_one(self, identifier: str) -> BookingOutputSchema | None:
        # selectinload fetches passengers and tickets in two extra queries
        # instead of one lazy pair per row later (the N+1 trap).
        statement = (
            select(Booking)
            .where(Booking.booking_key == identifier)
            .options(
                selectinload(Booking.passengers),
                selectinload(Booking.tickets),
                selectinload(Booking.discount_code),
            )
        )
        booking = self.session.scalars(statement).one_or_none()
        if booking is None:
            return None
        # Dict form: ORM ``discount_code`` is a relationship, API wants the string.
        return BookingOutputSchema.model_validate(
            {
                "booking_key": booking.booking_key,
                "pnr": booking.pnr,
                "status": booking.status,
                "total_amount": booking.total_amount,
                "currency": booking.currency,
                "discount_amount": booking.discount_amount,
                "discount_code": booking.discount_code.code if booking.discount_code is not None else None,
                "expires_at": booking.expires_at,
                "confirmed_at": booking.confirmed_at,
                "created_at": booking.created_at,
                "passengers": booking.passengers,
                "tickets": booking.tickets,
            }
        )

    def get_by_key_or_raise(self, booking_key: str) -> BookingOutputSchema:
        return self.get_one_or_raise(booking_key)
