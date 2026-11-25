"""Booking data primitives: create rows, look bookings up, release inventory.

Everything here flushes and never commits — the caller owns the transaction.
"""

from collections import Counter
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select

from minirail.inventory.models import OD
from minirail.inventory.service.seat_inventory import release_seats
from minirail.orm import MinirailSession
from minirail.sales.models import Booking, DiscountCode, Passenger, Ticket


def get_booking_by_key(session: MinirailSession, booking_key: str) -> Booking | None:
    """Load a booking by its public key."""
    statement = select(Booking).where(Booking.booking_key == booking_key)
    return session.scalars(statement).one_or_none()


def get_booking_by_id(session: MinirailSession, booking_id: int) -> Booking | None:
    statement = select(Booking).where(Booking.id == booking_id)
    return session.scalars(statement).one_or_none()


def create_booking_rows(
    session: MinirailSession,
    *,
    sales_channel_id: int,
    od: OD,
    passenger_names: list[tuple[str, str]],
    expires_at: datetime,
    total_amount: Decimal,
    min_price: Decimal,
    discount: DiscountCode | None = None,
    discount_amount: Decimal | None = None,
) -> Booking:
    """Create the PENDING booking with its passengers and HELD tickets.

    Seat inventory and discount quota are NOT touched here — hold_seats() /
    reserve_discount_use() are separate primitives and the job composes them.

    ``total_amount`` is the amount charged (after any discount). Ticket
    ``price_at_sale`` stays the OD list price regardless of promo.
    """
    booking = Booking(
        sales_channel_id=sales_channel_id,
        total_amount=total_amount,
        currency=od.currency,
        min_price=min_price,
        discount_code_id=None if discount is None else discount.id,
        discount_amount=discount_amount,
        expires_at=expires_at,
    )
    session.add(booking)
    for first_name, last_name in passenger_names:
        passenger = Passenger(booking=booking, first_name=first_name, last_name=last_name)
        session.add(passenger)
        session.add(Ticket(booking=booking, passenger=passenger, od=od, price_at_sale=od.price))
    session.flush()
    return booking


def release_seats_for_booking(session: MinirailSession, booking: Booking) -> None:
    """Give back every seat this booking holds, one release per distinct OD."""
    seat_count_by_od_id = Counter(ticket.od_id for ticket in booking.tickets)
    for od_id, seat_count in seat_count_by_od_id.items():
        od = session.get_one(OD, od_id)
        release_seats(session, od, seat_count)
