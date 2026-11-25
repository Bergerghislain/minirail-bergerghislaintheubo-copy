from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from minirail.inventory.fetcher.trip_search import TripSearchFetcher
from minirail.inventory.schemas.trip import TripResultSchema
from minirail.utils.api import session_transaction
from minirail.utils.auth import CurrentSalesChannel

router = APIRouter(prefix="/api/trips", tags=["inventory"])


@router.get("/search")
def search_trips(
    sales_channel: CurrentSalesChannel,
    session: Annotated[Session, Depends(session_transaction)],
    origin_station_code: Annotated[str, Query(alias="originStationCode", min_length=5, max_length=5)],
    destination_station_code: Annotated[str, Query(alias="destinationStationCode", min_length=5, max_length=5)],
    travel_date: Annotated[date, Query(alias="date")],
    limit: Annotated[int | None, Query(ge=1, le=200)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TripResultSchema]:
    """All bookable trips between two stations on a given date.

    Response shape is a JSON array (same contract as the starter codebase), so
    clients can keep using ``response[0].odId``. Optional ``limit`` / ``offset``
    only slice that array — they never wrap it in a page object.
    """
    results = TripSearchFetcher(session).search(origin_station_code, destination_station_code, travel_date)
    if limit is None and offset == 0:
        return results
    end = None if limit is None else offset + limit
    return results[offset:end]
