from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from minirail.inventory.models import OD, Leg
from tests.sales.conftest import create_booking_via_api


def _leg_counts(session: Session, od: OD) -> list[int]:
    legs = session.scalars(select(Leg).where(Leg.service_id == od.service_id).order_by(Leg.rank)).all()
    return [leg.seats_booked for leg in legs]


def test_cancel_pending_booking_releases_seats(
    client: TestClient, auth_headers: dict[str, str], session: Session, paris_marseille_od: OD
) -> None:
    body = create_booking_via_api(client, auth_headers, session, paris_marseille_od.id, passenger_count=2)
    assert _leg_counts(session, paris_marseille_od) == [2, 2]

    response = client.post(f"/api/bookings/{body['bookingKey']}/cancel", headers=auth_headers)

    assert response.status_code == 200
    cancelled = response.json()
    assert cancelled["status"] == "CANCELLED"
    assert all(ticket["status"] == "CANCELLED" for ticket in cancelled["tickets"])
    assert _leg_counts(session, paris_marseille_od) == [0, 0]


def test_cancel_confirmed_booking_releases_seats(
    client: TestClient, auth_headers: dict[str, str], session: Session, paris_marseille_od: OD
) -> None:
    body = create_booking_via_api(client, auth_headers, session, paris_marseille_od.id, passenger_count=2)
    assert (
        client.post(
            f"/api/bookings/{body['bookingKey']}/confirm", headers=auth_headers, json={"paymentToken": "tok_ok"}
        ).status_code
        == 200
    )

    response = client.post(f"/api/bookings/{body['bookingKey']}/cancel", headers=auth_headers)

    assert response.status_code == 200
    assert _leg_counts(session, paris_marseille_od) == [0, 0]


def test_cancel_twice_is_409(
    client: TestClient, auth_headers: dict[str, str], session: Session, paris_marseille_od: OD
) -> None:
    body = create_booking_via_api(client, auth_headers, session, paris_marseille_od.id)
    assert client.post(f"/api/bookings/{body['bookingKey']}/cancel", headers=auth_headers).status_code == 200

    response = client.post(f"/api/bookings/{body['bookingKey']}/cancel", headers=auth_headers)

    assert response.status_code == 409
    assert response.json()["errorCode"] == "booking_not_pending"
    # Seats must NOT be released twice.
    assert _leg_counts(session, paris_marseille_od) == [0, 0]
