from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from minirail.inventory.models import OD


def test_idempotency_key_replays_the_same_booking(
    client: TestClient, auth_headers: dict[str, str], session: Session, paris_marseille_od: OD
) -> None:
    headers = {**auth_headers, "Idempotency-Key": "book-once"}
    payload = {
        "odId": paris_marseille_od.id,
        "passengers": [{"firstName": "Ada", "lastName": "Lovelace"}],
    }
    first = client.post("/api/bookings/", headers=headers, json=payload)
    assert first.status_code == 201, first.text
    second = client.post("/api/bookings/", headers=headers, json=payload)
    assert second.status_code == 201, second.text
    assert second.json()["bookingKey"] == first.json()["bookingKey"]
    session.expire_all()


def test_idempotency_key_conflict_on_different_body(
    client: TestClient, auth_headers: dict[str, str], session: Session, paris_marseille_od: OD
) -> None:
    headers = {**auth_headers, "Idempotency-Key": "book-conflict"}
    first_payload = {
        "odId": paris_marseille_od.id,
        "passengers": [{"firstName": "Ada", "lastName": "Lovelace"}],
    }
    assert client.post("/api/bookings/", headers=headers, json=first_payload).status_code == 201
    response = client.post(
        "/api/bookings/",
        headers=headers,
        json={
            "odId": paris_marseille_od.id,
            "passengers": [{"firstName": "Alan", "lastName": "Turing"}],
        },
    )
    assert response.status_code == 409
    assert response.json()["errorCode"] == "idempotency_conflict"
    session.expire_all()
