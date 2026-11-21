"""Builders for realistic domain object graphs used across test files."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from itertools import pairwise
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from minirail.inventory.models import OD, Leg, Route, Service, Station

_UTC = ZoneInfo("UTC")


def build_service_with_ods(
    session: Session,
    *,
    station_codes: list[str] | None = None,
    service_date: date | None = None,
    seat_capacity: int = 6,
    price_per_leg: Decimal = Decimal("40.00"),
) -> Service:
    """Create a service calling at `station_codes`, with one leg between each
    consecutive pair and one OD for every (origin, destination) pair.

    With the default 3 stations this produces 2 legs and 3 ODs, one of which
    (first station → last station) spans both legs — the multi-leg case.
    Stations are created (or reused if a station with that code exists).
    """
    codes = station_codes or ["FRAAA", "FRBBB", "FRCCC"]
    if len(codes) < 2:
        raise ValueError("A service needs at least two stations")
    when = service_date or (date.today() + timedelta(days=7))

    stations: list[Station] = []
    for code in codes:
        station = session.query(Station).filter_by(code=code).one_or_none()
        if station is None:
            station = Station(code=code, name=f"City {code[2:]}", timezone="Europe/Paris")
            session.add(station)
        stations.append(station)

    route = Route(code=f"{codes[0][2:]}-{codes[-1][2:]}", name=f"{codes[0]} to {codes[-1]}")
    service = Service(route=route, service_date=when, train_number="6103")
    session.add(service)

    first_departure = datetime.combine(when, time(hour=9), tzinfo=_UTC)
    legs: list[Leg] = []
    for rank, (origin, destination) in enumerate(pairwise(stations), start=1):
        leg = Leg(
            service=service,
            rank=rank,
            origin_station=origin,
            destination_station=destination,
            departure_at=first_departure + timedelta(hours=2 * (rank - 1)),
            arrival_at=first_departure + timedelta(hours=2 * rank - 1),
            seat_capacity=seat_capacity,
        )
        session.add(leg)
        legs.append(leg)

    for i, origin in enumerate(stations):
        for j in range(i + 1, len(stations)):
            leg_count = j - i
            session.add(
                OD(
                    service=service,
                    origin_station=origin,
                    destination_station=stations[j],
                    first_leg_rank=i + 1,
                    last_leg_rank=j,
                    price=price_per_leg * leg_count,
                )
            )

    session.flush()
    return service
