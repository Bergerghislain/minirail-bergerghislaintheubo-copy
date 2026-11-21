"""Seat inventory primitives: the only code allowed to touch Leg.seats_booked.

Everything here flushes and never commits — the caller owns the transaction.
"""

from sqlalchemy import select

from minirail.inventory.models import OD, Leg
from minirail.orm import MinirailSession
from minirail.utils.exc import SoldOutException


def get_legs_for_od(session: MinirailSession, od: OD) -> list[Leg]:
    """The legs spanned by `od`, in rank order."""
    statement = (
        select(Leg)
        .where(Leg.service_id == od.service_id, Leg.rank.between(od.first_leg_rank, od.last_leg_rank))
        .order_by(Leg.id)
    )
    return list(session.scalars(statement).all())


def hold_seats(session: MinirailSession, od: OD, seat_count: int) -> None:
    """Reserve `seat_count` seats on every leg the OD spans.

    Raises SoldOutException if any spanned leg lacks capacity.
    """
    for leg in get_legs_for_od(session, od):
        if leg.seat_capacity - leg.seats_booked < seat_count:
            raise SoldOutException(
                f"Not enough seats on leg {leg.origin_station.code}->{leg.destination_station.code}: "
                f"{leg.seat_capacity - leg.seats_booked} left, {seat_count} requested"
            )
        leg.seats_booked += seat_count
    session.flush()


def release_seats(session: MinirailSession, od: OD, seat_count: int) -> None:
    """Give back seats previously held on the OD's legs (expiry/cancellation)."""
    for leg in get_legs_for_od(session, od):
        leg.seats_booked -= seat_count
    session.flush()
