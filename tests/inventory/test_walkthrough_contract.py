"""Contract tests for the README walkthrough: search stays a JSON array."""

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.helpers import build_service_with_ods

TRAVEL_DATE = date.today() + timedelta(days=7)


def test_walkthrough_search_returns_json_array_with_od_id(
    client: TestClient, auth_headers: dict[str, str], session: Session
) -> None:
    build_service_with_ods(session, station_codes=["FRPAR", "FRLYS", "FRMRS"], service_date=TRAVEL_DATE)

    response = client.get(
        "/api/trips/search",
        headers=auth_headers,
        params={
            "originStationCode": "FRPAR",
            "destinationStationCode": "FRMRS",
            "date": TRAVEL_DATE.isoformat(),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    assert "odId" in body[0]

    # Walkthrough step 2: book using response[0].odId
    od_id = body[0]["odId"]
    booking = client.post(
        "/api/bookings/",
        headers={**auth_headers, "Content-Type": "application/json"},
        json={
            "odId": od_id,
            "passengers": [
                {"firstName": "Ada", "lastName": "Lovelace"},
                {"firstName": "Alan", "lastName": "Turing"},
            ],
        },
    )
    assert booking.status_code == 201
    assert booking.json()["status"] == "PENDING"
    assert "bookingKey" in booking.json()


def test_search_limit_offset_slice_keeps_json_array(
    client: TestClient, auth_headers: dict[str, str], session: Session
) -> None:
    build_service_with_ods(session, station_codes=["FRPAR", "FRLYS", "FRMRS"], service_date=TRAVEL_DATE)
    params = {
        "originStationCode": "FRPAR",
        "destinationStationCode": "FRMRS",
        "date": TRAVEL_DATE.isoformat(),
    }

    limited = client.get("/api/trips/search", headers=auth_headers, params={**params, "limit": 1})
    assert limited.status_code == 200
    body = limited.json()
    # Must remain a bare array — never a page wrapper like {"items":..., "total":...}.
    assert isinstance(body, list)
    assert len(body) == 1
    assert "odId" in body[0]
    assert "items" not in body[0]

    offset_past_end = client.get("/api/trips/search", headers=auth_headers, params={**params, "offset": 100})
    assert offset_past_end.status_code == 200
    assert offset_past_end.json() == []
