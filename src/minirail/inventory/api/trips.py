from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from minirail.inventory.fetcher.trip_search import TripSearchFetcher
from minirail.inventory.schemas.trip import TripSearchPageSchema
from minirail.utils.api import session_transaction
from minirail.utils.app import get_app
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
) -> TripSearchPageSchema:
    """Bookable trips between two stations on a given date (paginated)."""
    page_size = limit if limit is not None else get_app().configuration.api.search_page_size
    results = TripSearchFetcher(session).search(origin_station_code, destination_station_code, travel_date)
    page = results[offset : offset + page_size]
    return TripSearchPageSchema(items=page, total=len(results), limit=page_size, offset=offset)
