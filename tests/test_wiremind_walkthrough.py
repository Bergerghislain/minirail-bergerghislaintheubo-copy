"""Wiremind / README walkthrough compatibility check.

Mirrors the curl sequence in README.md exactly: search → book → confirm,
then a second booking with SAVE10. Trip search must remain a bare JSON array
(``response[0]["odId"]``), not a page object.
"""

from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from minirail.sales.models import SalesChannel
from tests.factories import DiscountCodeFactory
from tests.helpers import build_service_with_ods

TRAVEL_DATE = date.today() + timedelta(days=1)


def _channel(session: Session, auth_headers: dict[str, str]) -> SalesChannel:
    return session.scalars(select(SalesChannel).where(SalesChannel.api_key == auth_headers["X-API-Key"])).one()


def test_readme_walkthrough_wiremind_compatible(
    client: TestClient, auth_headers: dict[str, str], session: Session
) -> None:
    build_service_with_ods(session, station_codes=["FRPAR", "FRLYS", "FRMRS"], service_date=TRAVEL_DATE)

    # 1. GET /api/trips/search → JSON array; clients index [0]["odId"].
    search = client.get(
        "/api/trips/search",
        headers=auth_headers,
        params={
            "originStationCode": "FRPAR",
            "destinationStationCode": "FRMRS",
            "date": TRAVEL_DATE.isoformat(),
        },
    )
    assert search.status_code == 200
    trips = search.json()
    assert isinstance(trips, list)
    od_id = trips[0]["odId"]
    assert isinstance(od_id, int)

    # 2. POST /api/bookings/ without discount → 201 PENDING + bookingKey + discountAmount.
    create = client.post(
        "/api/bookings/",
        headers=auth_headers,
        json={
            "odId": od_id,
            "passengers": [
                {"firstName": "Ada", "lastName": "Lovelace"},
                {"firstName": "Alan", "lastName": "Turing"},
            ],
        },
    )
    assert create.status_code == 201, create.text
    booking = create.json()
    assert booking["status"] == "PENDING"
    assert "bookingKey" in booking
    assert "discountAmount" in booking
    assert booking["discountAmount"] == "0.00"
    assert booking["discountCode"] is None
    full_total = Decimal(booking["totalAmount"])
    assert full_total == Decimal("160.00")

    # 3. POST confirm with tok_ok → CONFIRMED (one shot).
    confirm = client.post(
        f"/api/bookings/{booking['bookingKey']}/confirm",
        headers=auth_headers,
        json={"paymentToken": "tok_ok"},
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["status"] == "CONFIRMED"

    # Confirm is one-shot: a second attempt must fail.
    again = client.post(
        f"/api/bookings/{booking['bookingKey']}/confirm",
        headers=auth_headers,
        json={"paymentToken": "tok_ok"},
    )
    assert again.status_code == 409

    # 4. Another booking with SAVE10 (DiscountCodeFactory) → discounted total.
    DiscountCodeFactory(sales_channel=_channel(session, auth_headers), code="SAVE10", percent_off=Decimal("10.00"))
    discounted = client.post(
        "/api/bookings/",
        headers=auth_headers,
        json={
            "odId": od_id,
            "passengers": [
                {"firstName": "Ada", "lastName": "Lovelace"},
                {"firstName": "Alan", "lastName": "Turing"},
            ],
            "discountCode": "SAVE10",
        },
    )
    assert discounted.status_code == 201, discounted.text
    body = discounted.json()
    assert body["status"] == "PENDING"
    assert body["discountCode"] == "SAVE10"
    assert body["discountAmount"] == "16.00"
    assert Decimal(body["totalAmount"]) == Decimal("144.00")
    assert Decimal(body["totalAmount"]) < full_total

    # Confirm still one shot on the discounted booking.
    confirm_discounted = client.post(
        f"/api/bookings/{body['bookingKey']}/confirm",
        headers=auth_headers,
        json={"paymentToken": "tok_ok"},
    )
    assert confirm_discounted.status_code == 200, confirm_discounted.text
    assert confirm_discounted.json()["status"] == "CONFIRMED"
    assert (
        client.post(
            f"/api/bookings/{body['bookingKey']}/confirm",
            headers=auth_headers,
            json={"paymentToken": "tok_ok"},
        ).status_code
        == 409
    )


def test_openapi_trip_search_returns_array_schema(client: TestClient) -> None:
    """OpenAPI must advertise a JSON array for GET /api/trips/search."""
    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    schema = openapi.json()
    search_op = schema["paths"]["/api/trips/search"]["get"]
    success = search_op["responses"]["200"]["content"]["application/json"]["schema"]
    # FastAI may inline or $ref; either way the top-level type must be array.
    if "$ref" in success:
        ref_name = success["$ref"].rsplit("/", 1)[-1]
        success = schema["components"]["schemas"][ref_name]
    assert success.get("type") == "array"
    assert "items" in success
