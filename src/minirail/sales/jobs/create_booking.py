from dataclasses import dataclass
from datetime import timedelta
from typing import ClassVar, override

from minirail.inventory.models import OD, ServiceStatusEnum
from minirail.inventory.service.seat_inventory import hold_seats
from minirail.orm import MinirailSession
from minirail.sales.models import Booking
from minirail.sales.schemas.booking import PassengerInputSchema
from minirail.sales.service.booking import create_booking_rows
from minirail.utils.app import get_app
from minirail.utils.date_utils import utc_now
from minirail.utils.exc import ItemNotFoundException, SoldOutException
from minirail.utils.job import BaseJob


@dataclass(kw_only=True)
class CreateBookingJob(BaseJob[Booking]):
    """Create a PENDING booking: hold one seat per passenger on every leg the
    OD spans, then create the booking, passengers and HELD tickets.

    The capacity check happens inside hold_seats(); trip search results are
    advisory. The booking holds its seats until confirmation or until
    expires_at, when the expiry actor releases them.
    """

    business_exceptions: ClassVar = (ItemNotFoundException, SoldOutException)

    session: MinirailSession
    sales_channel_id: int
    od_id: int
    passengers: list[PassengerInputSchema]

    @override
    def _call(self) -> None:
        od = self.session.get(OD, self.od_id)
        if od is None or od.service.status is not ServiceStatusEnum.SCHEDULED:
            raise ItemNotFoundException(f"OD {self.od_id} not found or not bookable")

        hold_seats(self.session, od, len(self.passengers))

        ttl = timedelta(seconds=get_app().configuration.api.booking_ttl_seconds)
        booking = create_booking_rows(
            self.session,
            sales_channel_id=self.sales_channel_id,
            od=od,
            passenger_names=[(p.first_name, p.last_name) for p in self.passengers],
            expires_at=utc_now() + ttl,
        )
        self.set_output(booking)
