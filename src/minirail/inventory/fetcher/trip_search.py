from datetime import date
from typing import ClassVar, override

from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from minirail.inventory.models import OD, Leg, Service, ServiceStatusEnum, Station
from minirail.inventory.schemas.trip import TripResultSchema
from minirail.utils.fetcher import SQLBaseFetcher


class TripSearchFetcher(SQLBaseFetcher[TripResultSchema]):
    """Availability search: every sellable OD between two stations on a date.

    Results are cached for a short time; every booking-path write invalidates
    the whole group (`TripSearchFetcher.expire()`), so the TTL only matters
    when an invalidation is missed. Remaining seats are advisory either way —
    the booking flow re-checks capacity (see
    minirail.inventory.service.seat_inventory).
    """

    cache_enabled: ClassVar[bool] = True
    cache_ttl_seconds: ClassVar[int] = 60

    @property
    @override
    def output_schema(self) -> type[TripResultSchema]:
        return TripResultSchema

    def search(self, origin_code: str, destination_code: str, travel_date: date) -> list[TripResultSchema]:
        identifier = f"{origin_code}::{destination_code}::{travel_date.isoformat()}"
        cached = self._cached_list(identifier)
        if cached is not None:
            return cached
        results = self._search(origin_code, destination_code, travel_date)
        self._store_list(identifier, results)
        return results

    def _search(self, origin_code: str, destination_code: str, travel_date: date) -> list[TripResultSchema]:
        origin = aliased(Station)
        destination = aliased(Station)
        # An OD spans the legs whose rank lies in [first_leg_rank, last_leg_rank];
        # its availability is the *minimum* remaining seats across those legs,
        # and its departure/arrival are the first leg's departure and the last
        # leg's arrival.
        statement = (
            select(
                OD.id,
                Service.train_number,
                Service.service_date,
                origin.code.label("origin_code"),
                destination.code.label("destination_code"),
                func.min(Leg.departure_at).label("departure_at"),
                func.max(Leg.arrival_at).label("arrival_at"),
                OD.price,
                OD.currency,
                func.min(Leg.seat_capacity - Leg.seats_booked).label("remaining_seats"),
            )
            .join(Service, OD.service_id == Service.id)
            .join(origin, OD.origin_station_id == origin.id)
            .join(destination, OD.destination_station_id == destination.id)
            .join(
                Leg,
                (Leg.service_id == OD.service_id) & Leg.rank.between(OD.first_leg_rank, OD.last_leg_rank),
            )
            .where(
                origin.code == origin_code,
                destination.code == destination_code,
                Service.service_date == travel_date,
                Service.status == ServiceStatusEnum.SCHEDULED,
            )
            .group_by(OD.id, Service.train_number, Service.service_date, origin.code, destination.code)
            .order_by(func.min(Leg.departure_at))
        )
        return [
            TripResultSchema(
                od_id=row.id,
                train_number=row.train_number,
                service_date=row.service_date,
                origin_station_code=row.origin_code,
                destination_station_code=row.destination_code,
                departure_at=row.departure_at,
                arrival_at=row.arrival_at,
                price=row.price,
                currency=row.currency,
                remaining_seats=row.remaining_seats,
            )
            for row in self.session.execute(statement)
        ]
