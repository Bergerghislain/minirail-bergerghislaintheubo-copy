from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from minirail.inventory.models import OD
from minirail.sales.jobs.expire_booking import ExpireBookingJob
from minirail.sales.models import Booking, DiscountCode, SalesChannel
from minirail.utils.date_utils import utc_now
from tests.factories import DiscountCodeFactory, SalesChannelFactory
from tests.sales.conftest import create_booking_via_api


def _channel_for_headers(session: Session, auth_headers: dict[str, str]) -> SalesChannel:
    api_key = auth_headers["X-API-Key"]
    return session.scalars(select(SalesChannel).where(SalesChannel.api_key == api_key)).one()


def test_create_booking_with_discount_code(
    client: TestClient, auth_headers: dict[str, str], session: Session, paris_marseille_od: OD
) -> None:
    channel = _channel_for_headers(session, auth_headers)
    DiscountCodeFactory(sales_channel=channel, code="SAVE10", percent_off=Decimal("10.00"), max_uses=5)

    body = create_booking_via_api(
        client, auth_headers, session, paris_marseille_od.id, passenger_count=2, discount_code="save10"
    )

    # 2 passengers x 80.00 = 160.00, 10% off => 16.00 discount, total 144.00
    assert body["totalAmount"] == "144.00"
    assert body["discountAmount"] == "16.00"
    assert body["discountCode"] == "SAVE10"

    discount = session.scalars(select(DiscountCode).where(DiscountCode.code == "SAVE10")).one()
    assert discount.use_count == 1


def test_discount_code_exhausted(
    client: TestClient, auth_headers: dict[str, str], session: Session, paris_marseille_od: OD
) -> None:
    channel = _channel_for_headers(session, auth_headers)
    DiscountCodeFactory(sales_channel=channel, code="ONCE", percent_off=Decimal("20.00"), max_uses=1)

    create_booking_via_api(
        client, auth_headers, session, paris_marseille_od.id, passenger_count=1, discount_code="ONCE"
    )

    payload = {
        "odId": paris_marseille_od.id,
        "passengers": [{"firstName": "A", "lastName": "B"}],
        "discountCode": "ONCE",
    }
    response = client.post("/api/bookings/", headers=auth_headers, json=payload)

    assert response.status_code == 409
    assert response.json()["errorCode"] == "discount_code_exhausted"


def test_unknown_discount_code_is_400(client: TestClient, auth_headers: dict[str, str], paris_marseille_od: OD) -> None:
    payload = {
        "odId": paris_marseille_od.id,
        "passengers": [{"firstName": "A", "lastName": "B"}],
        "discountCode": "NOPE",
    }
    response = client.post("/api/bookings/", headers=auth_headers, json=payload)

    assert response.status_code == 400
    assert response.json()["errorCode"] == "invalid_discount_code"


def test_discount_code_from_other_channel_is_rejected(
    client: TestClient, auth_headers: dict[str, str], session: Session, paris_marseille_od: OD
) -> None:
    other = SalesChannelFactory()
    DiscountCodeFactory(sales_channel=other, code="OTHER10", percent_off=Decimal("10.00"), max_uses=5)

    payload = {
        "odId": paris_marseille_od.id,
        "passengers": [{"firstName": "A", "lastName": "B"}],
        "discountCode": "OTHER10",
    }
    response = client.post("/api/bookings/", headers=auth_headers, json=payload)

    assert response.status_code == 400
    assert response.json()["errorCode"] == "invalid_discount_code"


def test_cancel_pending_booking_releases_discount_use(
    client: TestClient, auth_headers: dict[str, str], session: Session, paris_marseille_od: OD
) -> None:
    channel = _channel_for_headers(session, auth_headers)
    DiscountCodeFactory(sales_channel=channel, code="FREE10", percent_off=Decimal("10.00"), max_uses=3)

    body = create_booking_via_api(
        client, auth_headers, session, paris_marseille_od.id, passenger_count=1, discount_code="FREE10"
    )
    discount = session.scalars(select(DiscountCode).where(DiscountCode.code == "FREE10")).one()
    assert discount.use_count == 1

    assert client.post(f"/api/bookings/{body['bookingKey']}/cancel", headers=auth_headers).status_code == 200
    session.expire_all()

    discount = session.scalars(select(DiscountCode).where(DiscountCode.code == "FREE10")).one()
    assert discount.use_count == 0


def test_expire_pending_booking_releases_discount_use(
    client: TestClient, auth_headers: dict[str, str], session: Session, paris_marseille_od: OD
) -> None:
    channel = _channel_for_headers(session, auth_headers)
    DiscountCodeFactory(sales_channel=channel, code="TTL10", percent_off=Decimal("10.00"), max_uses=3)

    body = create_booking_via_api(
        client, auth_headers, session, paris_marseille_od.id, passenger_count=1, discount_code="TTL10"
    )
    booking = session.scalars(select(Booking).where(Booking.booking_key == body["bookingKey"])).one()
    booking.expires_at = utc_now()  # due now
    session.flush()

    result = ExpireBookingJob(session=session, booking_id=booking.id).call()
    assert result.success is True
    assert result.output is True
    session.expire_all()

    discount = session.scalars(select(DiscountCode).where(DiscountCode.code == "TTL10")).one()
    assert discount.use_count == 0


def test_confirm_then_cancel_keeps_discount_use(
    client: TestClient, auth_headers: dict[str, str], session: Session, paris_marseille_od: OD
) -> None:
    channel = _channel_for_headers(session, auth_headers)
    DiscountCodeFactory(sales_channel=channel, code="KEEP10", percent_off=Decimal("10.00"), max_uses=3)

    body = create_booking_via_api(
        client, auth_headers, session, paris_marseille_od.id, passenger_count=1, discount_code="KEEP10"
    )
    assert (
        client.post(
            f"/api/bookings/{body['bookingKey']}/confirm",
            headers=auth_headers,
            json={"paymentToken": "tok_ok"},
        ).status_code
        == 200
    )
    assert client.post(f"/api/bookings/{body['bookingKey']}/cancel", headers=auth_headers).status_code == 200
    session.expire_all()

    discount = session.scalars(select(DiscountCode).where(DiscountCode.code == "KEEP10")).one()
    assert discount.use_count == 1
