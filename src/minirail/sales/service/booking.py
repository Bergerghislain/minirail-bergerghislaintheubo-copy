"""Booking data primitives: create rows, look bookings up, release inventory.

Everything here flushes and never commits — the caller owns the transaction.
"""

from collections import Counter
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from minirail.inventory.models import OD
from minirail.inventory.service.seat_inventory import release_seats
from minirail.orm import MinirailSession
from minirail.sales.models import Booking, Passenger, Ticket


def get_booking_by_key(session: MinirailSession, booking_key: str) -> Booking | None:
    """Load a booking by its public key, with its discount code when it has one."""
    statement = select(Booking).where(Booking.booking_key == booking_key).options(selectinload(Booking.discount_code))
    return session.scalars(statement).one_or_none()


def get_booking_by_id(session: MinirailSession, booking_id: int) -> Booking | None:
    statement = select(Booking).where(Booking.id == booking_id).options(selectinload(Booking.discount_code))
    return session.scalars(statement).one_or_none()


def create_booking_rows(
    session: MinirailSession,
    *,
    sales_channel_id: int,
    od: OD,
    passenger_names: list[tuple[str, str]],
    expires_at: datetime,
    discount_code_id: int | None = None,
    discount_amount: Decimal = Decimal("0.00"),
    min_price: Decimal = Decimal("0.00"),
) -> Booking:
    """Create the PENDING booking with its passengers and HELD tickets.

    Seat inventory is NOT touched here — hold_seats() is a separate primitive
    and the job composes the two. The total is the full OD price minus the
    discount the caller already computed; tickets keep the catalogue price.
    """
    booking = Booking(
        sales_channel_id=sales_channel_id,
        total_amount=od.price * len(passenger_names) - discount_amount,
        currency=od.currency,
        discount_code_id=discount_code_id,
        discount_amount=discount_amount,
        min_price=min_price,
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
