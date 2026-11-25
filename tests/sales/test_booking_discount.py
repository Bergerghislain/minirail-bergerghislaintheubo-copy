from datetime import timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from minirail.inventory.models import OD
from minirail.sales.jobs.expire_booking import ExpireBookingJob
from minirail.sales.models import Booking, BookingStatusEnum, DiscountCode
from minirail.sales.service.discount_code import compute_discount_amount
from minirail.utils.app import get_app
from minirail.utils.date_utils import utc_now
from tests.factories import DiscountCodeFactory, SalesChannelFactory
from tests.sales.conftest import create_booking_via_api


def test_compute_discount_amount_rounds_half_up() -> None:
    # 10% of 19.95 = 1.995 → 2.00
    assert compute_discount_amount(Decimal("19.95"), 10) == Decimal("2.00")
    # 10% of 10.00 = 1.00
    assert compute_discount_amount(Decimal("10.00"), 10) == Decimal("1.00")


def test_create_booking_with_discount(client: TestClient, session: Session, paris_marseille_od: OD) -> None:
    channel = SalesChannelFactory()
    DiscountCodeFactory(sales_channel=channel, code="SAVE10", percent_off=10, max_uses=100)
    headers = {"X-API-Key": channel.api_key}

    body = create_booking_via_api(
        client, headers, session, paris_marseille_od.id, passenger_count=2, discount_code="save10"
    )

    # Gross 160.00, 10% off → 16.00 discount, 144.00 charged.
    assert body["totalAmount"] == "144.00"
    assert body["discountAmount"] == "16.00"
    assert body["discountCode"] == "SAVE10"
    # Ticket list prices are unchanged.
    assert [ticket["priceAtSale"] for ticket in body["tickets"]] == ["80.00", "80.00"]

    discount = session.scalars(select(DiscountCode).where(DiscountCode.code == "SAVE10")).one()
    assert discount.use_count == 1


def test_create_booking_invalid_discount_is_400(client: TestClient, session: Session, paris_marseille_od: OD) -> None:
    channel = SalesChannelFactory()
    headers = {"X-API-Key": channel.api_key}
    payload = {
        "odId": paris_marseille_od.id,
        "passengers": [{"firstName": "Ada", "lastName": "Lovelace"}],
        "discountCode": "NOPE",
    }

    response = client.post("/api/bookings/", headers=headers, json=payload)

    assert response.status_code == 400
    assert response.json()["errorCode"] == "invalid_discount_code"


def test_create_booking_exhausted_discount_is_409(client: TestClient, session: Session, paris_marseille_od: OD) -> None:
    channel = SalesChannelFactory()
    DiscountCodeFactory(sales_channel=channel, code="SAVE10", max_uses=1, use_count=1)
    headers = {"X-API-Key": channel.api_key}
    payload = {
        "odId": paris_marseille_od.id,
        "passengers": [{"firstName": "Ada", "lastName": "Lovelace"}],
        "discountCode": "SAVE10",
    }

    response = client.post("/api/bookings/", headers=headers, json=payload)

    assert response.status_code == 409
    assert response.json()["errorCode"] == "discount_code_exhausted"


def test_create_booking_below_min_price_is_400(client: TestClient, session: Session, paris_marseille_od: OD) -> None:
    channel = SalesChannelFactory()
    DiscountCodeFactory(sales_channel=channel, code="SAVE10", percent_off=10)
    headers = {"X-API-Key": channel.api_key}
    original = get_app().configuration.api.discount_min_price
    get_app().configuration.api.discount_min_price = Decimal("200.00")
    try:
        payload = {
            "odId": paris_marseille_od.id,
            "passengers": [{"firstName": "Ada", "lastName": "Lovelace"}],
            "discountCode": "SAVE10",
        }
        response = client.post("/api/bookings/", headers=headers, json=payload)
    finally:
        get_app().configuration.api.discount_min_price = original

    assert response.status_code == 400
    assert response.json()["errorCode"] == "discount_not_applicable"


def test_cancel_pending_releases_discount_use(client: TestClient, session: Session, paris_marseille_od: OD) -> None:
    channel = SalesChannelFactory()
    DiscountCodeFactory(sales_channel=channel, code="SAVE10", percent_off=10)
    headers = {"X-API-Key": channel.api_key}
    body = create_booking_via_api(
        client, headers, session, paris_marseille_od.id, passenger_count=1, discount_code="SAVE10"
    )
    assert session.scalars(select(DiscountCode).where(DiscountCode.code == "SAVE10")).one().use_count == 1

    response = client.post(f"/api/bookings/{body['bookingKey']}/cancel", headers=headers)

    assert response.status_code == 200
    session.expire_all()
    assert session.scalars(select(DiscountCode).where(DiscountCode.code == "SAVE10")).one().use_count == 0


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

    response = client.post(f"/api/bookings/{body['bookingKey']}/cancel", headers=headers)

    assert response.status_code == 200
    session.expire_all()
    assert session.scalars(select(DiscountCode).where(DiscountCode.code == "SAVE10")).one().use_count == 1


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
    assert session.scalars(select(DiscountCode).where(DiscountCode.code == "SAVE10")).one().use_count == 0
