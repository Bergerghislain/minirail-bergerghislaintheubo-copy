from datetime import timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from minirail.inventory.models import OD, Leg
from minirail.sales.jobs.expire_booking import ExpireBookingJob
from minirail.sales.models import Booking, BookingStatusEnum, DiscountCode
from minirail.sales.service.discount_code import compute_discount_amount
from minirail.utils.app import get_app
from minirail.utils.date_utils import utc_now
from tests.factories import DiscountCodeFactory, SalesChannelFactory
from tests.sales.conftest import create_booking_via_api


def _booking_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Booking)) or 0


def _leg_counts(session: Session, od: OD) -> list[int]:
    legs = session.scalars(select(Leg).where(Leg.service_id == od.service_id).order_by(Leg.rank)).all()
    return [leg.seats_booked for leg in legs]


def _discount(session: Session, code: str = "SAVE10") -> DiscountCode:
    return session.scalars(select(DiscountCode).where(DiscountCode.code == code)).one()


def test_compute_discount_amount_rounds_half_up() -> None:
    # 10% of 19.95 = 1.995 → 2.00
    assert compute_discount_amount(Decimal("19.95"), 10) == Decimal("2.00")
    assert compute_discount_amount(Decimal("10.00"), 10) == Decimal("1.00")


def test_create_booking_with_discount_happy_path_and_casing(
    client: TestClient, session: Session, paris_marseille_od: OD
) -> None:
    channel = SalesChannelFactory()
    discount = DiscountCodeFactory(sales_channel=channel, code="SAVE10", percent_off=10, max_uses=100)
    headers = {"X-API-Key": channel.api_key}

    body = create_booking_via_api(
        client, headers, session, paris_marseille_od.id, passenger_count=2, discount_code="  save10  "
    )

    # Gross 160.00, 10% off → 16.00 discount, 144.00 charged.
    assert body["status"] == "PENDING"
    assert body["totalAmount"] == "144.00"
    assert body["discountAmount"] == "16.00"
    assert body["discountCode"] == "SAVE10"
    assert [ticket["priceAtSale"] for ticket in body["tickets"]] == ["80.00", "80.00"]

    booking = session.scalars(select(Booking).where(Booking.booking_key == body["bookingKey"])).one()
    assert booking.total_amount == Decimal("144.00")
    assert booking.discount_amount == Decimal("16.00")
    assert booking.discount_code_id == discount.id
    assert booking.min_price == get_app().configuration.api.discount_min_price
    assert _discount(session).use_count == 1


def test_create_booking_without_discount_code(client: TestClient, session: Session, paris_marseille_od: OD) -> None:
    channel = SalesChannelFactory()
    DiscountCodeFactory(sales_channel=channel, code="SAVE10", percent_off=10)
    headers = {"X-API-Key": channel.api_key}

    body = create_booking_via_api(client, headers, session, paris_marseille_od.id, passenger_count=2)

    assert body["totalAmount"] == "160.00"
    assert body["discountAmount"] is None
    assert body["discountCode"] is None

    booking = session.scalars(select(Booking).where(Booking.booking_key == body["bookingKey"])).one()
    assert booking.total_amount == Decimal("160.00")
    assert booking.discount_amount is None
    assert booking.discount_code_id is None
    assert _discount(session).use_count == 0


def test_create_booking_unknown_discount_is_400(client: TestClient, session: Session, paris_marseille_od: OD) -> None:
    channel = SalesChannelFactory()
    headers = {"X-API-Key": channel.api_key}
    before = _booking_count(session)

    response = client.post(
        "/api/bookings/",
        headers=headers,
        json={
            "odId": paris_marseille_od.id,
            "passengers": [{"firstName": "Ada", "lastName": "Lovelace"}],
            "discountCode": "NOPE",
        },
    )

    assert response.status_code == 400
    assert response.json()["errorCode"] == "invalid_discount_code"
    session.expire_all()
    assert _booking_count(session) == before
    assert _leg_counts(session, paris_marseille_od) == [0, 0]


def test_create_booking_other_channel_discount_is_400(
    client: TestClient, session: Session, paris_marseille_od: OD
) -> None:
    owner = SalesChannelFactory()
    other = SalesChannelFactory()
    DiscountCodeFactory(sales_channel=owner, code="SAVE10", percent_off=10)
    headers = {"X-API-Key": other.api_key}
    before = _booking_count(session)

    response = client.post(
        "/api/bookings/",
        headers=headers,
        json={
            "odId": paris_marseille_od.id,
            "passengers": [{"firstName": "Ada", "lastName": "Lovelace"}],
            "discountCode": "SAVE10",
        },
    )

    assert response.status_code == 400
    assert response.json()["errorCode"] == "invalid_discount_code"
    session.expire_all()
    assert _booking_count(session) == before
    assert _discount(session).use_count == 0


def test_create_booking_inactive_discount_is_400(client: TestClient, session: Session, paris_marseille_od: OD) -> None:
    channel = SalesChannelFactory()
    DiscountCodeFactory(sales_channel=channel, code="SAVE10", percent_off=10, is_active=False)
    headers = {"X-API-Key": channel.api_key}

    response = client.post(
        "/api/bookings/",
        headers=headers,
        json={
            "odId": paris_marseille_od.id,
            "passengers": [{"firstName": "Ada", "lastName": "Lovelace"}],
            "discountCode": "SAVE10",
        },
    )

    assert response.status_code == 400
    assert response.json()["errorCode"] == "invalid_discount_code"
    session.expire_all()
    assert _discount(session).use_count == 0
    assert _leg_counts(session, paris_marseille_od) == [0, 0]


def test_create_booking_expired_discount_is_400(client: TestClient, session: Session, paris_marseille_od: OD) -> None:
    channel = SalesChannelFactory()
    DiscountCodeFactory(
        sales_channel=channel,
        code="SAVE10",
        percent_off=10,
        valid_until=utc_now() - timedelta(minutes=1),
    )
    headers = {"X-API-Key": channel.api_key}

    response = client.post(
        "/api/bookings/",
        headers=headers,
        json={
            "odId": paris_marseille_od.id,
            "passengers": [{"firstName": "Ada", "lastName": "Lovelace"}],
            "discountCode": "SAVE10",
        },
    )

    assert response.status_code == 400
    assert response.json()["errorCode"] == "invalid_discount_code"
    session.expire_all()
    assert _discount(session).use_count == 0


def test_create_booking_exhausted_discount_is_409(client: TestClient, session: Session, paris_marseille_od: OD) -> None:
    channel = SalesChannelFactory()
    DiscountCodeFactory(sales_channel=channel, code="SAVE10", max_uses=1, use_count=1)
    headers = {"X-API-Key": channel.api_key}
    before = _booking_count(session)

    response = client.post(
        "/api/bookings/",
        headers=headers,
        json={
            "odId": paris_marseille_od.id,
            "passengers": [{"firstName": "Ada", "lastName": "Lovelace"}],
            "discountCode": "SAVE10",
        },
    )

    assert response.status_code == 409
    assert response.json()["errorCode"] == "discount_code_exhausted"
    session.expire_all()
    assert _booking_count(session) == before
    assert _discount(session).use_count == 1
    assert _leg_counts(session, paris_marseille_od) == [0, 0]


def test_create_booking_below_min_price_is_400(client: TestClient, session: Session, paris_marseille_od: OD) -> None:
    channel = SalesChannelFactory()
    DiscountCodeFactory(sales_channel=channel, code="SAVE10", percent_off=10)
    headers = {"X-API-Key": channel.api_key}
    original = get_app().configuration.api.discount_min_price
    get_app().configuration.api.discount_min_price = Decimal("200.00")
    try:
        response = client.post(
            "/api/bookings/",
            headers=headers,
            json={
                "odId": paris_marseille_od.id,
                "passengers": [{"firstName": "Ada", "lastName": "Lovelace"}],
                "discountCode": "SAVE10",
            },
        )
    finally:
        get_app().configuration.api.discount_min_price = original

    assert response.status_code == 400
    assert response.json()["errorCode"] == "discount_not_applicable"
    session.expire_all()
    assert _discount(session).use_count == 0
    assert _leg_counts(session, paris_marseille_od) == [0, 0]


def test_cancel_pending_releases_discount_use(client: TestClient, session: Session, paris_marseille_od: OD) -> None:
    channel = SalesChannelFactory()
    DiscountCodeFactory(sales_channel=channel, code="SAVE10", percent_off=10)
    headers = {"X-API-Key": channel.api_key}
    body = create_booking_via_api(
        client, headers, session, paris_marseille_od.id, passenger_count=1, discount_code="SAVE10"
    )
    assert _discount(session).use_count == 1

    response = client.post(f"/api/bookings/{body['bookingKey']}/cancel", headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"
    session.expire_all()
    assert _discount(session).use_count == 0
    booking = session.scalars(select(Booking).where(Booking.booking_key == body["bookingKey"])).one()
    assert booking.discount_amount == Decimal("8.00")  # snapshot kept; use was released
    assert booking.status is BookingStatusEnum.CANCELLED


def test_expire_pending_releases_discount_use(client: TestClient, session: Session, paris_marseille_od: OD) -> None:
    channel = SalesChannelFactory()
    DiscountCodeFactory(sales_channel=channel, code="SAVE10", percent_off=10)
    headers = {"X-API-Key": channel.api_key}
    body = create_booking_via_api(
        client, headers, session, paris_marseille_od.id, passenger_count=1, discount_code="SAVE10"
    )
    booking = session.scalars(select(Booking).where(Booking.booking_key == body["bookingKey"])).one()
    booking.expires_at = utc_now() - timedelta(seconds=1)
    session.flush()

    result = ExpireBookingJob(session=session, booking_id=booking.id).call()

    assert result.output is True
    assert booking.status is BookingStatusEnum.EXPIRED
    assert _discount(session).use_count == 0


def test_cancel_confirmed_keeps_discount_use(client: TestClient, session: Session, paris_marseille_od: OD) -> None:
    channel = SalesChannelFactory()
    DiscountCodeFactory(sales_channel=channel, code="SAVE10", percent_off=10)
    headers = {"X-API-Key": channel.api_key}
    body = create_booking_via_api(
        client, headers, session, paris_marseille_od.id, passenger_count=1, discount_code="SAVE10"
    )
    assert (
        client.post(
            f"/api/bookings/{body['bookingKey']}/confirm", headers=headers, json={"paymentToken": "tok_ok"}
        ).status_code
        == 200
    )
    assert _discount(session).use_count == 1

    response = client.post(f"/api/bookings/{body['bookingKey']}/cancel", headers=headers)

    assert response.status_code == 200
    session.expire_all()
    assert _discount(session).use_count == 1
    booking = session.scalars(select(Booking).where(Booking.booking_key == body["bookingKey"])).one()
    assert booking.total_amount == Decimal("72.00")
    assert booking.discount_amount == Decimal("8.00")
    assert booking.status is BookingStatusEnum.CANCELLED
