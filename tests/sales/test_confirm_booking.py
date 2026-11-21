from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from minirail.inventory.models import OD
from minirail.sales.models import Booking
from minirail.utils.date_utils import utc_now
from tests.sales.conftest import create_booking_via_api


def _confirm(client: TestClient, headers: dict[str, str], booking_key: str, token: str = "tok_ok") -> Any:
    return client.post(f"/api/bookings/{booking_key}/confirm", headers=headers, json={"paymentToken": token})


def test_confirm_booking_happy_path(
    client: TestClient,
    auth_headers: dict[str, str],
    session: Session,
    paris_marseille_od: OD,
    sent_messages: list[tuple[Any, int | None]],
) -> None:
    body = create_booking_via_api(client, auth_headers, session, paris_marseille_od.id)

    response = _confirm(client, auth_headers, body["bookingKey"])

    assert response.status_code == 200, response.text
    confirmed = response.json()
    assert confirmed["status"] == "CONFIRMED"
    assert confirmed["confirmedAt"] is not None
    assert confirmed["expiresAt"] is None
    assert all(ticket["status"] == "CONFIRMED" for ticket in confirmed["tickets"])

    notifications = [m for m, _ in sent_messages if m.actor_name == "send_booking_notification"]
    assert len(notifications) == 1
    assert notifications[0].args[1] == "booking.confirmed"


def test_confirm_booking_payment_declined(
    client: TestClient, auth_headers: dict[str, str], session: Session, paris_marseille_od: OD
) -> None:
    body = create_booking_via_api(client, auth_headers, session, paris_marseille_od.id)

    response = _confirm(client, auth_headers, body["bookingKey"], token="tok_declined")

    assert response.status_code == 409
    assert response.json()["errorCode"] == "payment_declined"
    # Still PENDING: the customer can retry with another card.
    still = client.get(f"/api/bookings/{body['bookingKey']}", headers=auth_headers).json()
    assert still["status"] == "PENDING"


def test_confirm_booking_twice_is_409(
    client: TestClient, auth_headers: dict[str, str], session: Session, paris_marseille_od: OD
) -> None:
    body = create_booking_via_api(client, auth_headers, session, paris_marseille_od.id)
    assert _confirm(client, auth_headers, body["bookingKey"]).status_code == 200

    response = _confirm(client, auth_headers, body["bookingKey"])

    assert response.status_code == 409
    assert response.json()["errorCode"] == "booking_not_pending"


def test_confirm_expired_hold_is_409(
    client: TestClient, auth_headers: dict[str, str], session: Session, paris_marseille_od: OD
) -> None:
    body = create_booking_via_api(client, auth_headers, session, paris_marseille_od.id)
    booking = session.scalars(select(Booking).where(Booking.booking_key == body["bookingKey"])).one()
    booking.expires_at = utc_now() - timedelta(seconds=1)
    session.commit()

    response = _confirm(client, auth_headers, body["bookingKey"])

    assert response.status_code == 409
    assert response.json()["errorCode"] == "booking_not_pending"


def test_confirm_unknown_booking_is_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = _confirm(client, auth_headers, "does-not-exist")
    assert response.status_code == 404
