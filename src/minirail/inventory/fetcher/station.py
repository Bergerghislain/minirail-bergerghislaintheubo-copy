from typing import ClassVar, override

from sqlalchemy import select

from minirail.inventory.models import Station
from minirail.inventory.schemas.station import StationSchema
from minirail.utils.fetcher import SQLOneFetcher


class StationFetcher(SQLOneFetcher[StationSchema]):
    """Stations barely ever change: cache aggressively."""

    cache_enabled: ClassVar[bool] = True
    cache_ttl_seconds: ClassVar[int] = 3600

    @property
    @override
    def output_schema(self) -> type[StationSchema]:
        return StationSchema

    @override
    def _fetch_one(self, identifier: str) -> StationSchema | None:
        station = self.session.scalars(select(Station).where(Station.code == identifier)).one_or_none()
        return StationSchema.model_validate(station) if station is not None else None

    def get_all(self) -> list[StationSchema]:
        cached = self._cached_list("all")
        if cached is not None:
            return cached
        stations = self.session.scalars(select(Station).order_by(Station.code)).all()
        result = [StationSchema.model_validate(station) for station in stations]
        self._store_list("all", result)
        return result
