from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import ClassVar, override

from minirail.inventory.models import OD, ServiceStatusEnum
from minirail.inventory.service.seat_inventory import hold_seats
from minirail.orm import MinirailSession
from minirail.sales.models import Booking, DiscountCode
from minirail.sales.schemas.booking import PassengerInputSchema
from minirail.sales.service.booking import create_booking_rows
from minirail.sales.service.discount_code import (
    check_minimum_price,
    compute_discount_amount,
    get_valid_discount_code_for_update,
    reserve_discount_use,
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
    """Create a PENDING booking: hold one seat per passenger on every leg the
    OD spans, then create the booking, passengers and HELD tickets.

    The capacity check happens inside hold_seats(); trip search results are
    advisory. The booking holds its seats until confirmation or until
    expires_at, when the expiry actor releases them.

    An optional discount code is validated against the calling sales channel,
    reserves one use, and is applied as a percentage off the booking total.
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

        hold_seats(self.session, od, len(self.passengers))

        full_amount = od.price * len(self.passengers)
        # Snapshotted on every booking, with or without a code: it records the
        # rule the sale was made under, even after the configuration changes.
        min_price = get_app().configuration.api.discount_min_price

        discount: DiscountCode | None = None
        discount_amount = Decimal("0.00")
        if self.discount_code is not None:
            check_minimum_price(full_amount=full_amount, min_price=min_price)
            discount = get_valid_discount_code_for_update(
                self.session,
                code=self.discount_code,
                sales_channel_id=self.sales_channel_id,
            )
            discount_amount = compute_discount_amount(full_amount=full_amount, percent_off=discount.percent_off)
            reserve_discount_use(self.session, discount)

        ttl = timedelta(seconds=get_app().configuration.api.booking_ttl_seconds)
        booking = create_booking_rows(
            self.session,
            sales_channel_id=self.sales_channel_id,
            od=od,
            passenger_names=[(p.first_name, p.last_name) for p in self.passengers],
            expires_at=utc_now() + ttl,
            discount_code_id=discount.id if discount is not None else None,
            discount_amount=discount_amount,
            min_price=min_price,
        )
        self.set_output(booking)
