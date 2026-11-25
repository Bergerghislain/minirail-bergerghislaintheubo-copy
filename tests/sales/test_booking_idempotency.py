from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from minirail.inventory.models import OD
from minirail.sales.models import Booking
from tests.factories import SalesChannelFactory


def _payload(od_id: int, last_name: str = "Lovelace") -> dict[str, Any]:
    return {
        "odId": od_id,
        "passengers": [{"firstName": "Ada", "lastName": last_name}],
    }


def test_idempotency_replay_returns_same_booking(
    client: TestClient, session: Session, paris_marseille_od: OD, sent_messages: list[tuple[Any, int | None]]
) -> None:
    channel = SalesChannelFactory()
    headers = {"X-API-Key": channel.api_key, "Idempotency-Key": "book-once-1"}
    payload = _payload(paris_marseille_od.id)

    first = client.post("/api/bookings/", headers=headers, json=payload)
    assert first.status_code == 201, first.text
    first_body = first.json()

    expiry_after_first = len([m for m, _ in sent_messages if m.actor_name == "expire_booking"])

    second = client.post("/api/bookings/", headers=headers, json=payload)
    assert second.status_code == 200, second.text
    second_body = second.json()

    assert second_body["bookingKey"] == first_body["bookingKey"]
    assert second_body["pnr"] == first_body["pnr"]
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(Booking)) == 1
    # Replay must not schedule another expiry message.
    expiry_after_second = len([m for m, _ in sent_messages if m.actor_name == "expire_booking"])
    assert expiry_after_second == expiry_after_first


def test_idempotency_conflict_different_body(client: TestClient, session: Session, paris_marseille_od: OD) -> None:
    channel = SalesChannelFactory()
    headers = {"X-API-Key": channel.api_key, "Idempotency-Key": "book-once-2"}

    first = client.post("/api/bookings/", headers=headers, json=_payload(paris_marseille_od.id, "Lovelace"))
    assert first.status_code == 201, first.text

    conflict = client.post("/api/bookings/", headers=headers, json=_payload(paris_marseille_od.id, "Hopper"))
    assert conflict.status_code == 409
    assert conflict.json()["errorCode"] == "idempotency_key_conflict"
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(Booking)) == 1


def test_idempotency_keys_are_scoped_per_channel(client: TestClient, session: Session, paris_marseille_od: OD) -> None:
    channel_a = SalesChannelFactory()
    channel_b = SalesChannelFactory()
    payload = _payload(paris_marseille_od.id)

    first = client.post(
        "/api/bookings/",
        headers={"X-API-Key": channel_a.api_key, "Idempotency-Key": "shared-key"},
        json=payload,
    )
    second = client.post(
        "/api/bookings/",
        headers={"X-API-Key": channel_b.api_key, "Idempotency-Key": "shared-key"},
        json=payload,
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["bookingKey"] != second.json()["bookingKey"]
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(Booking)) == 2
