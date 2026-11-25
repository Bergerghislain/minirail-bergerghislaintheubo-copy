from datetime import date, datetime
from decimal import Decimal

from minirail.utils.schema import Schema


class TripResultSchema(Schema):
    od_id: int
    train_number: str
    service_date: date
    origin_station_code: str
    destination_station_code: str
    departure_at: datetime
    arrival_at: datetime
    price: Decimal
    currency: str
    # Advisory only: computed at search time and possibly cached — the
    # capacity check happens when the booking is created.
    remaining_seats: int


class TripSearchPageSchema(Schema):
    """Paginated trip search response."""

    items: list[TripResultSchema]
    total: int
    limit: int
    offset: int
