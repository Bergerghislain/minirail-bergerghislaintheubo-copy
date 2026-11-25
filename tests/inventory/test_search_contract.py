"""Wiremind walkthrough contract: search must stay a JSON array.

Their README curl / scripts do ``response[0].odId``. A page object would break
that without lowering the rest of the hardening work.
"""

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.helpers import build_service_with_ods

TRAVEL_DATE = date.today() + timedelta(days=7)


def test_search_response_is_a_json_array_with_od_id(
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
    assert not isinstance(body, dict)  # never a page wrapper
    assert body[0]["odId"] > 0
