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
    reserve_discount_use,
    validate_discount_code,
)
from minirail.utils.app import get_app
from minirail.utils.date_utils import utc_now
from minirail.utils.exc import (
    DiscountCodeExhaustedException,
    DiscountNotApplicableException,
    InvalidDiscountCodeException,
    ItemNotFoundException,
    SoldOutException,
)
from minirail.utils.job import BaseJob


@dataclass(kw_only=True)
class CreateBookingJob(BaseJob[Booking]):
    """Create a PENDING booking: hold seats, optionally reserve a discount use,
    then create the booking, passengers and HELD tickets.

    Lock order is stable: seats first, then the discount row (FOR UPDATE), so
    concurrent bookings cannot deadlock on crossed lock acquisition.
    """

    business_exceptions: ClassVar = (
        ItemNotFoundException,
        SoldOutException,
        InvalidDiscountCodeException,
        DiscountCodeExhaustedException,
        DiscountNotApplicableException,
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

        passenger_count = len(self.passengers)
        hold_seats(self.session, od, passenger_count)

        gross_total = od.price * passenger_count
        min_price = get_app().configuration.api.discount_min_price
        discount = None
        discount_amount: Decimal | None = None
        total_amount = gross_total

        if self.discount_code is not None:
            discount = validate_discount_code(
                self.session,
                sales_channel_id=self.sales_channel_id,
                code=self.discount_code,
                booking_total=gross_total,
                min_price=min_price,
            )
            discount_amount = compute_discount_amount(gross_total, discount.percent_off)
            total_amount = gross_total - discount_amount

        ttl = timedelta(seconds=get_app().configuration.api.booking_ttl_seconds)
        booking = create_booking_rows(
            self.session,
            sales_channel_id=self.sales_channel_id,
            od=od,
            passenger_names=[(p.first_name, p.last_name) for p in self.passengers],
            expires_at=utc_now() + ttl,
            total_amount=total_amount,
            min_price=min_price,
            discount=discount,
            discount_amount=discount_amount,
        )
        if discount is not None:
            # Journal needs booking.id; reserve after the booking row exists.
            reserve_discount_use(self.session, discount, booking)
        self.set_output(booking)
