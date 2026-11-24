from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import ClassVar, override

from minirail.inventory.models import OD, ServiceStatusEnum
from minirail.inventory.service.seat_inventory import hold_seats
from minirail.orm import MinirailSession
from minirail.sales.models import Booking
from minirail.sales.schemas.booking import PassengerInputSchema
from minirail.sales.service.booking import create_booking_rows
from minirail.sales.service.discount_code import (
    compute_discount_amount,
    get_discount_code_for_update,
    reserve_discount_use,
)
from minirail.utils.app import get_app
from minirail.utils.date_utils import utc_now
from minirail.utils.exc import (
    DiscountCodeExhaustedException,
    InvalidDiscountCodeException,
    ItemNotFoundException,
    SoldOutException,
)
from minirail.utils.job import BaseJob

# Same threshold as Booking.min_price's ORM default — centralized on Booking.
_MIN_PRICE = Decimal("0.00")


@dataclass(kw_only=True)
class CreateBookingJob(BaseJob[Booking]):
    """Create a PENDING booking: hold one seat per passenger on every leg the
    OD spans, then create the booking, passengers and HELD tickets.

    The capacity check happens inside hold_seats(); trip search results are
    advisory. The booking holds its seats until confirmation or until
    expires_at, when the expiry actor releases them.

    An optional discount_code is validated against the sales channel, reserved
    (use_count += 1), and applied as a percent-off on the booking total.
    """

    business_exceptions: ClassVar = (
        ItemNotFoundException,
        SoldOutException,
        InvalidDiscountCodeException,
        DiscountCodeExhaustedException,
    )

    session: MinirailSession
    sales_channel_id: int
    od_id: int
    passengers: list[PassengerInputSchema]
    discount_code: str | None = None

    @override
    def _call(self) -> None:
        od = self.session.get(OD, self.od_id)
        if od is None or od.service.status is not ServiceStatusEnum.SCHEDULED:
            raise ItemNotFoundException(f"OD {self.od_id} not found or not bookable")

        hold_seats(self.session, od, len(self.passengers))

        full_amount = od.price * len(self.passengers)
        discount_code_id: int | None = None
        discount_amount = Decimal("0.00")
        total_amount = full_amount

        if self.discount_code is not None:
            discount = get_discount_code_for_update(
                self.session,
                code=self.discount_code,
                sales_channel_id=self.sales_channel_id,
            )
            # Booking total must meet the centralized min_price threshold.
            if full_amount < _MIN_PRICE:
                raise InvalidDiscountCodeException(
                    f"A discount code needs a booking total of at least {_MIN_PRICE}, this one is {full_amount}"
                )
            discount_amount = compute_discount_amount(
                full_amount=full_amount,
                percent_off=discount.percent_off,
            )
            total_amount = full_amount - discount_amount
            reserve_discount_use(self.session, discount)
            discount_code_id = discount.id

        ttl = timedelta(seconds=get_app().configuration.api.booking_ttl_seconds)
        booking = create_booking_rows(
            self.session,
            sales_channel_id=self.sales_channel_id,
            od=od,
            passenger_names=[(p.first_name, p.last_name) for p in self.passengers],
            expires_at=utc_now() + ttl,
            discount_code_id=discount_code_id,
            discount_amount=discount_amount,
            total_amount=total_amount,
        )
        self.set_output(booking)
