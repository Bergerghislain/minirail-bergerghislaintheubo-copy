"""Demo dataset for local development (`minirail init-demo-data`).

Flushes only — the CLI command owns the transaction and commits.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from itertools import pairwise
from zoneinfo import ZoneInfo

from sqlalchemy import select

from minirail.inventory.models import OD, Leg, Route, Service, Station
from minirail.orm import MinirailSession
from minirail.sales.jobs.confirm_booking import ClaimConfirmBookingJob, FinalizeConfirmBookingJob
from minirail.sales.jobs.create_booking import CreateBookingJob
from minirail.sales.models import DiscountCode, SalesChannel
from minirail.sales.schemas.booking import PassengerInputSchema
from minirail.utils import payments

DEMO_API_KEY = "demo-channel-key"
DEMO_DISCOUNT_CODE = "SAVE10"
DEMO_DAYS = 14
SEAT_CAPACITY = 6  # small on purpose: sold-out situations are reachable by hand

_UTC = ZoneInfo("UTC")

_STATIONS = [
    ("FRPAR", "Paris Gare de Lyon", "Europe/Paris"),
    ("FRLYS", "Lyon Part-Dieu", "Europe/Paris"),
    ("FRMRS", "Marseille Saint-Charles", "Europe/Paris"),
    ("FRLIL", "Lille Flandres", "Europe/Paris"),
    ("FRNTE", "Nantes", "Europe/Paris"),
    ("FRBOR", "Bordeaux Saint-Jean", "Europe/Paris"),
    ("FRSTR", "Strasbourg", "Europe/Paris"),
    ("FRNCE", "Nice-Ville", "Europe/Paris"),
]

# route code -> (name, station codes along the way, price of each direct hop)
_ROUTES: dict[str, tuple[str, list[str], list[Decimal]]] = {
    "PAR-MRS": ("Paris - Marseille via Lyon", ["FRPAR", "FRLYS", "FRMRS"], [Decimal("45.00"), Decimal("39.00")]),
    "PAR-LIL": ("Paris - Lille", ["FRPAR", "FRLIL"], [Decimal("35.00")]),
}
# Full-span OD prices when the route has more than one leg (cheaper than the sum).
_FULL_SPAN_PRICES = {"PAR-MRS": Decimal("79.00")}

_TRAINS_PER_DAY = {"PAR-MRS": ["6103", "6157"], "PAR-LIL": ["7205", "7261"]}
_DEPARTURE_HOURS = [8, 16]


@dataclass
class DemoSummary:
    api_key: str
    service_count: int
    first_date: date
    sample_search_od: tuple[str, str]
    confirmed_booking_key: str
    pending_booking_key: str
    discount_code: str


def demo_data_exists(session: MinirailSession) -> bool:
    return session.scalars(select(Station).where(Station.code == "FRPAR")).one_or_none() is not None


def create_demo_data(session: MinirailSession) -> DemoSummary:
    stations = {code: Station(code=code, name=name, timezone=tz) for code, name, tz in _STATIONS}
    session.add_all(stations.values())

    first_date = date.today() + timedelta(days=1)
    service_count = 0
    for route_code, (route_name, station_codes, hop_prices) in _ROUTES.items():
        route = Route(code=route_code, name=route_name)
        session.add(route)
        for day_offset in range(DEMO_DAYS):
            service_date = first_date + timedelta(days=day_offset)
            for train_number, departure_hour in zip(_TRAINS_PER_DAY[route_code], _DEPARTURE_HOURS, strict=True):
                _build_service(
                    session, route, service_date, train_number, departure_hour, station_codes, hop_prices, stations
                )
                service_count += 1
    session.flush()

    channel = SalesChannel(name="demo", api_key=DEMO_API_KEY)
    session.add(channel)
    session.flush()

    session.add(
        DiscountCode(
            sales_channel_id=channel.id,
            code=DEMO_DISCOUNT_CODE,
            percent_off=Decimal("10.00"),
            max_uses=100,
        )
    )
    session.flush()

    confirmed_key, pending_key = _create_sample_bookings(session, channel, stations, first_date)

    return DemoSummary(
        api_key=DEMO_API_KEY,
        service_count=service_count,
        first_date=first_date,
        sample_search_od=("FRPAR", "FRMRS"),
        confirmed_booking_key=confirmed_key,
        pending_booking_key=pending_key,
        discount_code=DEMO_DISCOUNT_CODE,
    )


def _build_service(
    session: MinirailSession,
    route: Route,
    service_date: date,
    train_number: str,
    departure_hour: int,
    station_codes: list[str],
    hop_prices: list[Decimal],
    stations: dict[str, Station],
) -> None:
    service = Service(route=route, service_date=service_date, train_number=train_number)
    session.add(service)

    departure = datetime.combine(service_date, time(hour=departure_hour), tzinfo=_UTC)
    for rank, (origin_code, destination_code) in enumerate(pairwise(station_codes), start=1):
        session.add(
            Leg(
                service=service,
                rank=rank,
                origin_station=stations[origin_code],
                destination_station=stations[destination_code],
                departure_at=departure + timedelta(hours=2 * (rank - 1)),
                arrival_at=departure + timedelta(hours=2 * rank - 1),
                seat_capacity=SEAT_CAPACITY,
            )
        )

    # One OD per (origin, destination) pair along the route.
    for i in range(len(station_codes) - 1):
        for j in range(i + 1, len(station_codes)):
            if i == 0 and j == len(station_codes) - 1 and route.code in _FULL_SPAN_PRICES:
                price = _FULL_SPAN_PRICES[route.code]
            else:
                price = sum(hop_prices[i:j], Decimal("0.00"))
            session.add(
                OD(
                    service=service,
                    origin_station=stations[station_codes[i]],
                    destination_station=stations[station_codes[j]],
                    first_leg_rank=i + 1,
                    last_leg_rank=j,
                    price=price,
                )
            )


def _create_sample_bookings(
    session: MinirailSession,
    channel: SalesChannel,
    stations: dict[str, Station],
    first_date: date,
) -> tuple[str, str]:
    """One CONFIRMED and one PENDING booking on tomorrow's first PAR->MRS train,
    so both lifecycle states are observable right after seeding."""
    od = session.scalars(
        select(OD)
        .join(Service, OD.service_id == Service.id)
        .where(
            Service.service_date == first_date,
            Service.train_number == "6103",
            OD.origin_station_id == stations["FRPAR"].id,
            OD.destination_station_id == stations["FRMRS"].id,
        )
    ).one()

    confirmed = CreateBookingJob(
        session=session,
        sales_channel_id=channel.id,
        od_id=od.id,
        passengers=[PassengerInputSchema(first_name="Grace", last_name="Hopper")],
    ).call_for_api()
    # Seed uses the same claim → charge → finalize shape as the API, without
    # separate commits: the CLI owns the surrounding transaction.
    claimed = ClaimConfirmBookingJob(session=session, booking_key=confirmed.booking_key).call_for_api()
    charge = payments.charge("tok_demo", claimed.total_amount, claimed.currency)
    if not charge.success:
        raise RuntimeError(f"Demo payment failed: {charge.failure_reason}")
    FinalizeConfirmBookingJob(session=session, booking_key=confirmed.booking_key).call_for_api()

    pending = CreateBookingJob(
        session=session,
        sales_channel_id=channel.id,
        od_id=od.id,
        passengers=[PassengerInputSchema(first_name="Alan", last_name="Turing")],
    ).call_for_api()

    return confirmed.booking_key, pending.booking_key
