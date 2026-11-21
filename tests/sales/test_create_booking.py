from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from minirail.inventory.models import OD, Leg
from minirail.sales.models import Booking
from minirail.utils.app import get_app
from tests.sales.conftest import create_booking_via_api


def test_create_booking_happy_path(
    client: TestClient,
    auth_headers: dict[str, str],
    session: Session,
    paris_marseille_od: OD,
    sent_messages: list[tuple[Any, int | None]],
) -> None:
    body = create_booking_via_api(client, auth_headers, session, paris_marseille_od.id, passenger_count=2)

    assert body["status"] == "PENDING"
    assert body["totalAmount"] == "160.00"  # 2 passengers x 80.00 (two legs at 40.00)
    assert len(body["pnr"]) == 6
    assert len(body["passengers"]) == 2
    assert [ticket["status"] for ticket in body["tickets"]] == ["HELD", "HELD"]
    assert body["expiresAt"] is not None

    # One seat per passenger held on BOTH spanned legs.
    legs = session.scalars(select(Leg).where(Leg.service_id == paris_marseille_od.service_id)).all()
    assert [leg.seats_booked for leg in legs] == [2, 2]

    # The expiry message is scheduled at creation time, delayed by the TTL.
    expiry_messages = [(m, delay) for m, delay in sent_messages if m.actor_name == "expire_booking"]
    assert len(expiry_messages) == 1
    booking = session.scalars(select(Booking).where(Booking.booking_key == body["bookingKey"])).one()
    assert expiry_messages[0][0].args == (booking.id,)
    assert expiry_messages[0][1] == get_app().configuration.api.booking_ttl_seconds * 1000


def test_create_booking_sold_out(
    client: TestClient, auth_headers: dict[str, str], session: Session, paris_marseille_od: OD
) -> None:
    create_booking_via_api(client, auth_headers, session, paris_marseille_od.id, passenger_count=4)

    payload = {"odId": paris_marseille_od.id, "passengers": [{"firstName": "A", "lastName": f"B{i}"} for i in range(3)]}
    response = client.post("/api/bookings/", headers=auth_headers, json=payload)

    assert response.status_code == 409
    assert response.json()["errorCode"] == "sold_out"
    # The failed attempt took nothing.
    legs = session.scalars(select(Leg).where(Leg.service_id == paris_marseille_od.service_id)).all()
    assert [leg.seats_booked for leg in legs] == [4, 4]


def test_create_booking_unknown_od_is_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    payload = {"odId": 999999, "passengers": [{"firstName": "A", "lastName": "B"}]}
    response = client.post("/api/bookings/", headers=auth_headers, json=payload)
    assert response.status_code == 404
    assert response.json()["errorCode"] == "item_not_found"


def test_create_booking_rejects_unknown_fields(
    client: TestClient, auth_headers: dict[str, str], paris_marseille_od: OD
) -> None:
    payload = {
        "odId": paris_marseille_od.id,
        "passengers": [{"firstName": "A", "lastName": "B"}],
        "seatPreference": "window",  # not part of the schema -> 422, not silently ignored
    }
    response = client.post("/api/bookings/", headers=auth_headers, json=payload)
    assert response.status_code == 422


def test_create_booking_requires_at_least_one_passenger(
    client: TestClient, auth_headers: dict[str, str], paris_marseille_od: OD
) -> None:
    response = client.post(
        "/api/bookings/", headers=auth_headers, json={"odId": paris_marseille_od.id, "passengers": []}
    )
    assert response.status_code == 422
