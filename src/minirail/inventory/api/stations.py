from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from minirail.inventory.fetcher.station import StationFetcher
from minirail.inventory.schemas.station import StationSchema
from minirail.utils.api import session_transaction
from minirail.utils.auth import CurrentSalesChannel

router = APIRouter(prefix="/api/stations", tags=["inventory"])


@router.get("/")
def list_stations(
    sales_channel: CurrentSalesChannel,
    session: Annotated[Session, Depends(session_transaction)],
) -> list[StationSchema]:
    return StationFetcher(session).get_all()
