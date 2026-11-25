from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from minirail.inventory.models import OD, Station
from tests.helpers import build_service_with_ods

TRAVEL_DATE = date.today() + timedelta(days=7)


@pytest.fixture
def paris_marseille_od(session: Session) -> OD:
    """A 2-leg service Paris→Lyon→Marseille; returns the full-span OD (capacity 6)."""
    service = build_service_with_ods(session, station_codes=["FRPAR", "FRLYS", "FRMRS"], service_date=TRAVEL_DATE)
    origin = session.scalars(select(Station).where(Station.code == "FRPAR")).one()
    destination = session.scalars(select(Station).where(Station.code == "FRMRS")).one()
    return session.scalars(
        select(OD).where(
            OD.service_id == service.id,
            OD.origin_station_id == origin.id,
            OD.destination_station_id == destination.id,
        )
    ).one()


def create_booking_via_api(
    client: TestClient,
    headers: dict[str, str],
    session: Session,
    od_id: int,
    passenger_count: int = 2,
    discount_code: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "odId": od_id,
        "passengers": [{"firstName": "Ada", "lastName": f"Lovelace-{i}"} for i in range(passenger_count)],
    }
    if discount_code is not None:
        payload["discountCode"] = discount_code
    response = client.post("/api/bookings/", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    # The request ran on a sibling session; expire this session's identity map
    # so the test re-reads current values instead of stale cached objects.
    session.expire_all()
    return response.json()
