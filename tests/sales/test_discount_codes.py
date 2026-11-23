from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from minirail.inventory.models import OD
from minirail.sales.jobs.expire_booking import ExpireBookingJob
from minirail.sales.models import Booking, DiscountCode, SalesChannel
from minirail.utils.app import App
from minirail.utils.date_utils import utc_now
from tests.factories import DiscountCodeFactory, SalesChannelFactory
from tests.sales.conftest import create_booking_via_api

# The paris_marseille_od fixture spans two legs at 40.00, so one passenger
# costs 80.00 and two cost 160.00.
ONE_PASSENGER_PRICE = Decimal("80.00")


def _channel(session: Session, auth_headers: dict[str, str]) -> SalesChannel:
    api_key = auth_headers["X-API-Key"]
    return session.scalars(select(SalesChannel).where(SalesChannel.api_key == api_key)).one()


def _discount(session: Session, code: str) -> DiscountCode:
    return session.scalars(select(DiscountCode).where(DiscountCode.code == code)).one()


def _booking(session: Session, booking_key: str) -> Booking:
    return session.scalars(select(Booking).where(Booking.booking_key == booking_key)).one()


def _post_booking(client: TestClient, headers: dict[str, str], od_id: int, code: str) -> dict[str, object]:
    response = client.post(
        "/api/bookings/",
        headers=headers,
        json={"odId": od_id, "passengers": [{"firstName": "Ada", "lastName": "Lovelace"}], "discountCode": code},
    )
    return {"status_code": response.status_code, "body": response.json()}


def test_booking_with_a_discount_code_pays_less(
    client: TestClient, auth_headers: dict[str, str], session: Session, paris_marseille_od: OD
) -> None:
    DiscountCodeFactory(sales_channel=_channel(session, auth_headers), code="SAVE10", percent_off=Decimal("10.00"))

    # Sent in lower case on purpose: codes are normalized before lookup.
    body = create_booking_via_api(
        client, auth_headers, session, paris_marseille_od.id, passenger_count=2, discount_code="save10"
    )

    assert body["totalAmount"] == "144.00"  # 160.00 minus 10%
    assert body["discountAmount"] == "16.00"
    assert body["discountCode"] == "SAVE10"
    assert _discount(session, "SAVE10").use_count == 1


def test_booking_without_a_discount_code_is_unchanged(
    client: TestClient, auth_headers: dict[str, str], session: Session, paris_marseille_od: OD
) -> None:
    body = create_booking_via_api(client, auth_headers, session, paris_marseille_od.id, passenger_count=2)

    assert body["totalAmount"] == "160.00"
    assert body["discountAmount"] == "0.00"
    assert body["discountCode"] is None


def test_discount_amount_is_rounded_to_cents(
    client: TestClient, auth_headers: dict[str, str], session: Session, paris_marseille_od: OD
) -> None:
    DiscountCodeFactory(sales_channel=_channel(session, auth_headers), code="THIRD", percent_off=Decimal("33.33"))

    body = create_booking_via_api(
        client, auth_headers, session, paris_marseille_od.id, passenger_count=2, discount_code="THIRD"
    )

    # 160.00 x 33.33% = 53.328, rounded half up.
    assert body["discountAmount"] == "53.33"
    assert body["totalAmount"] == "106.67"


def test_exhausted_code_is_refused(
    client: TestClient, auth_headers: dict[str, str], session: Session, paris_marseille_od: OD
) -> None:
    DiscountCodeFactory(sales_channel=_channel(session, auth_headers), code="ONCE", max_uses=1)
    create_booking_via_api(client, auth_headers, session, paris_marseille_od.id, 1, discount_code="ONCE")

    result = _post_booking(client, auth_headers, paris_marseille_od.id, "ONCE")

    assert result["status_code"] == 409
    assert result["body"]["errorCode"] == "discount_code_exhausted"  # pyright: ignore[reportIndexIssue]


@pytest.mark.parametrize(
    "factory_kwargs",
    [
        pytest.param({"is_active": False}, id="deactivated"),
        pytest.param({"valid_until": utc_now() - timedelta(days=1)}, id="out_of_date"),
    ],
)
def test_unusable_code_is_refused(
    client: TestClient,
    auth_headers: dict[str, str],
    session: Session,
    paris_marseille_od: OD,
    factory_kwargs: dict[str, object],
) -> None:
    DiscountCodeFactory(sales_channel=_channel(session, auth_headers), code="SHUT", **factory_kwargs)

    result = _post_booking(client, auth_headers, paris_marseille_od.id, "SHUT")

    assert result["status_code"] == 400
    assert result["body"]["errorCode"] == "invalid_discount_code"  # pyright: ignore[reportIndexIssue]


def test_unknown_code_is_refused(client: TestClient, auth_headers: dict[str, str], paris_marseille_od: OD) -> None:
    result = _post_booking(client, auth_headers, paris_marseille_od.id, "NOPE")

    assert result["status_code"] == 400
    assert result["body"]["errorCode"] == "invalid_discount_code"  # pyright: ignore[reportIndexIssue]


def test_another_channels_code_is_refused(
    client: TestClient, auth_headers: dict[str, str], session: Session, paris_marseille_od: OD
) -> None:
    DiscountCodeFactory(sales_channel=SalesChannelFactory(), code="THEIRS")

    result = _post_booking(client, auth_headers, paris_marseille_od.id, "THEIRS")

    assert result["status_code"] == 400
    assert result["body"]["errorCode"] == "invalid_discount_code"  # pyright: ignore[reportIndexIssue]
    assert _discount(session, "THEIRS").use_count == 0


def test_code_is_refused_below_the_minimum_price(
    client: TestClient,
    auth_headers: dict[str, str],
    session: Session,
    paris_marseille_od: OD,
    test_app: App,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(test_app.configuration.api, "discount_min_price", ONE_PASSENGER_PRICE + Decimal("1.00"))
    DiscountCodeFactory(sales_channel=_channel(session, auth_headers), code="RICH")

    result = _post_booking(client, auth_headers, paris_marseille_od.id, "RICH")

    assert result["status_code"] == 400
    assert result["body"]["errorCode"] == "discount_not_applicable"  # pyright: ignore[reportIndexIssue]
    assert _discount(session, "RICH").use_count == 0


def test_booking_records_the_minimum_price_that_applied(
    client: TestClient,
    auth_headers: dict[str, str],
    session: Session,
    paris_marseille_od: OD,
    test_app: App,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The threshold is configuration, but each sale keeps the value it was sold under."""
    monkeypatch.setattr(test_app.configuration.api, "discount_min_price", Decimal("50.00"))

    body = create_booking_via_api(client, auth_headers, session, paris_marseille_od.id, passenger_count=1)

    assert _booking(session, str(body["bookingKey"])).min_price == Decimal("50.00")
    assert "minPrice" not in body, "the threshold is an internal rule, not part of the contract"


def test_cancelling_a_pending_booking_gives_the_use_back(
    client: TestClient, auth_headers: dict[str, str], session: Session, paris_marseille_od: OD
) -> None:
    DiscountCodeFactory(sales_channel=_channel(session, auth_headers), code="FREE10")
    body = create_booking_via_api(client, auth_headers, session, paris_marseille_od.id, 1, discount_code="FREE10")
    assert _discount(session, "FREE10").use_count == 1

    assert client.post(f"/api/bookings/{body['bookingKey']}/cancel", headers=auth_headers).status_code == 200
    session.expire_all()

    assert _discount(session, "FREE10").use_count == 0


def test_expiring_a_pending_booking_gives_the_use_back(
    client: TestClient, auth_headers: dict[str, str], session: Session, paris_marseille_od: OD
) -> None:
    DiscountCodeFactory(sales_channel=_channel(session, auth_headers), code="TTL10")
    body = create_booking_via_api(client, auth_headers, session, paris_marseille_od.id, 1, discount_code="TTL10")
    booking = _booking(session, str(body["bookingKey"]))
    booking.expires_at = utc_now() - timedelta(seconds=1)
    session.flush()

    assert ExpireBookingJob(session=session, booking_id=booking.id).call().output is True
    session.expire_all()

    assert _discount(session, "TTL10").use_count == 0


def test_cancelling_a_confirmed_booking_keeps_the_use(
    client: TestClient, auth_headers: dict[str, str], session: Session, paris_marseille_od: OD
) -> None:
    """The promotion applied to a sale that was actually paid."""
    DiscountCodeFactory(sales_channel=_channel(session, auth_headers), code="KEEP10")
    body = create_booking_via_api(client, auth_headers, session, paris_marseille_od.id, 1, discount_code="KEEP10")

    confirm = client.post(
        f"/api/bookings/{body['bookingKey']}/confirm", headers=auth_headers, json={"paymentToken": "tok_ok"}
    )
    assert confirm.status_code == 200
    assert client.post(f"/api/bookings/{body['bookingKey']}/cancel", headers=auth_headers).status_code == 200
    session.expire_all()

    assert _discount(session, "KEEP10").use_count == 1
