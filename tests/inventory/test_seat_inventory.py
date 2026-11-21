import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from minirail.inventory.models import OD, Leg
from minirail.inventory.service.seat_inventory import hold_seats, release_seats
from minirail.utils.exc import SoldOutException
from tests.helpers import build_service_with_ods


def _od(session: Session, service_id: int, origin_code: str, destination_code: str) -> OD:
    from minirail.inventory.models import Station

    origin = session.scalars(select(Station).where(Station.code == origin_code)).one()
    destination = session.scalars(select(Station).where(Station.code == destination_code)).one()
    return session.scalars(
        select(OD).where(
            OD.service_id == service_id,
            OD.origin_station_id == origin.id,
            OD.destination_station_id == destination.id,
        )
    ).one()


def test_hold_seats_decrements_every_spanned_leg(session: Session) -> None:
    service = build_service_with_ods(session, station_codes=["FRPAR", "FRLYS", "FRMRS"])
    full_span = _od(session, service.id, "FRPAR", "FRMRS")

    hold_seats(session, full_span, 2)

    legs = session.scalars(select(Leg).where(Leg.service_id == service.id).order_by(Leg.rank)).all()
    assert [leg.seats_booked for leg in legs] == [2, 2]


def test_hold_seats_sold_out(session: Session) -> None:
    service = build_service_with_ods(session, station_codes=["FRPAR", "FRLYS"], seat_capacity=3)
    od = _od(session, service.id, "FRPAR", "FRLYS")

    hold_seats(session, od, 2)
    with pytest.raises(SoldOutException):
        hold_seats(session, od, 2)

    leg = session.scalars(select(Leg).where(Leg.service_id == service.id)).one()
    assert leg.seats_booked == 2, "the failed hold must not have taken anything"


def test_release_seats_restores_capacity(session: Session) -> None:
    service = build_service_with_ods(session, station_codes=["FRPAR", "FRLYS", "FRMRS"])
    full_span = _od(session, service.id, "FRPAR", "FRMRS")

    hold_seats(session, full_span, 3)
    release_seats(session, full_span, 3)

    legs = session.scalars(select(Leg).where(Leg.service_id == service.id)).all()
    assert all(leg.seats_booked == 0 for leg in legs)
