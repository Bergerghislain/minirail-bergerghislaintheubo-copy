from datetime import date, timedelta
from decimal import Decimal

import factory
from factory.alchemy import SQLAlchemyModelFactory

from minirail.inventory.models import OD, Leg, Route, Service, Station
from minirail.sales.models import Booking, DiscountCode, Passenger, SalesChannel, Ticket
from minirail.utils.date_utils import utc_now


class BaseFactory(SQLAlchemyModelFactory):
    class Meta:
        abstract = True
        # Flush (not commit): rows get their ids while staying inside the
        # test's transaction.
        sqlalchemy_session_persistence = "flush"


class StationFactory(BaseFactory):
    class Meta:
        model = Station

    code = factory.Sequence(lambda n: f"ST{n:03d}")
    name = factory.Sequence(lambda n: f"Station {n}")
    timezone = "Europe/Paris"


class RouteFactory(BaseFactory):
    class Meta:
        model = Route

    code = factory.Sequence(lambda n: f"RT-{n:03d}")
    name = factory.Sequence(lambda n: f"Route {n}")


class ServiceFactory(BaseFactory):
    class Meta:
        model = Service

    route = factory.SubFactory(RouteFactory)
    service_date = factory.LazyFunction(lambda: date.today() + timedelta(days=7))
    train_number = factory.Sequence(lambda n: f"{6100 + n}")


class LegFactory(BaseFactory):
    class Meta:
        model = Leg

    service = factory.SubFactory(ServiceFactory)
    rank = 1
    origin_station = factory.SubFactory(StationFactory)
    destination_station = factory.SubFactory(StationFactory)
    departure_at = factory.LazyFunction(lambda: utc_now() + timedelta(days=7))
    arrival_at = factory.LazyFunction(lambda: utc_now() + timedelta(days=7, hours=2))
    seat_capacity = 6
    seats_booked = 0


class ODFactory(BaseFactory):
    class Meta:
        model = OD

    service = factory.SubFactory(ServiceFactory)
    origin_station = factory.SubFactory(StationFactory)
    destination_station = factory.SubFactory(StationFactory)
    first_leg_rank = 1
    last_leg_rank = 1
    price = Decimal("45.00")


class SalesChannelFactory(BaseFactory):
    class Meta:
        model = SalesChannel

    name = factory.Sequence(lambda n: f"channel-{n}")
    api_key = factory.Sequence(lambda n: f"test-api-key-{n}")


class DiscountCodeFactory(BaseFactory):
    class Meta:
        model = DiscountCode

    sales_channel = factory.SubFactory(SalesChannelFactory)
    code = factory.Sequence(lambda n: f"PROMO{n}")
    percent_off = Decimal("10.00")
    max_uses = 10
    use_count = 0
    is_active = True


class BookingFactory(BaseFactory):
    class Meta:
        model = Booking

    sales_channel = factory.SubFactory(SalesChannelFactory)
    total_amount = Decimal("45.00")
    discount_amount = Decimal("0.00")
    expires_at = factory.LazyFunction(lambda: utc_now() + timedelta(minutes=15))


class PassengerFactory(BaseFactory):
    class Meta:
        model = Passenger

    booking = factory.SubFactory(BookingFactory)
    first_name = "Ada"
    last_name = factory.Sequence(lambda n: f"Lovelace-{n}")


class TicketFactory(BaseFactory):
    class Meta:
        model = Ticket

    booking = factory.SubFactory(BookingFactory)
    passenger = factory.SubFactory(PassengerFactory, booking=factory.SelfAttribute("..booking"))
    od = factory.SubFactory(ODFactory)
    price_at_sale = Decimal("45.00")


ALL_FACTORIES: list[type[BaseFactory]] = [
    StationFactory,
    RouteFactory,
    ServiceFactory,
    LegFactory,
    ODFactory,
    SalesChannelFactory,
    DiscountCodeFactory,
    BookingFactory,
    PassengerFactory,
    TicketFactory,
]
