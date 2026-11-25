from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from minirail.inventory.fetcher.trip_search import TripSearchFetcher
from minirail.inventory.models import Leg
from tests.helpers import build_service_with_ods

TRAVEL_DATE = date.today() + timedelta(days=7)


def _search(client: TestClient, headers: dict[str, str], origin: str, destination: str) -> list[dict[str, object]]:
    response = client.get(
        "/api/trips/search",
        headers=headers,
        params={"originStationCode": origin, "destinationStationCode": destination, "date": TRAVEL_DATE.isoformat()},
    )
    assert response.status_code == 200
    body = response.json()
    # Wiremind / README walkthrough: a JSON array, not a page object.
    assert isinstance(body, list)
    return body


def test_direct_od_availability(client: TestClient, auth_headers: dict[str, str], session: Session) -> None:
    build_service_with_ods(session, station_codes=["FRPAR", "FRLYS", "FRMRS"], service_date=TRAVEL_DATE)

    results = _search(client, auth_headers, "FRPAR", "FRLYS")

    assert len(results) == 1
    assert results[0]["remainingSeats"] == 6
    assert results[0]["price"] == "40.00"


def test_multi_leg_od_availability_is_min_over_legs(
    client: TestClient, auth_headers: dict[str, str], session: Session
) -> None:
    service = build_service_with_ods(session, station_codes=["FRPAR", "FRLYS", "FRMRS"], service_date=TRAVEL_DATE)
    # Take 4 seats on the second leg only: Paris→Marseille spans both legs, so
    # its availability must drop to min(6, 2) = 2.
    second_leg = session.query(Leg).filter_by(service_id=service.id, rank=2).one()
    second_leg.seats_booked = 4
    session.flush()

    results = _search(client, auth_headers, "FRPAR", "FRMRS")

    assert len(results) == 1
    assert results[0]["remainingSeats"] == 2
    assert results[0]["price"] == "80.00"  # two legs at 40.00 each


def test_search_filters_by_date(client: TestClient, auth_headers: dict[str, str], session: Session) -> None:
    build_service_with_ods(session, station_codes=["FRPAR", "FRLYS", "FRMRS"], service_date=TRAVEL_DATE)

    response = client.get(
        "/api/trips/search",
        headers=auth_headers,
        params={
            "originStationCode": "FRPAR",
            "destinationStationCode": "FRMRS",
            "date": (TRAVEL_DATE + timedelta(days=1)).isoformat(),
        },
    )

    assert response.status_code == 200
    assert response.json() == []


def test_optional_limit_still_returns_a_list(
    client: TestClient, auth_headers: dict[str, str], session: Session
) -> None:
    """Pagination must not change the response envelope — only the slice size."""
    build_service_with_ods(session, station_codes=["FRPAR", "FRLYS", "FRMRS"], service_date=TRAVEL_DATE)

    response = client.get(
        "/api/trips/search",
        headers=auth_headers,
        params={
            "originStationCode": "FRPAR",
            "destinationStationCode": "FRMRS",
            "date": TRAVEL_DATE.isoformat(),
            "limit": 1,
            "offset": 0,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert "odId" in body[0]


def test_search_results_are_cached(session: Session, query_counter: list[str]) -> None:
    build_service_with_ods(session, station_codes=["FRPAR", "FRLYS", "FRMRS"], service_date=TRAVEL_DATE)
    fetcher = TripSearchFetcher(session)

    first = fetcher.search("FRPAR", "FRMRS", TRAVEL_DATE)
    queries_after_first = len(query_counter)
    second = fetcher.search("FRPAR", "FRMRS", TRAVEL_DATE)

    assert first == second
    assert len(query_counter) == queries_after_first

    TripSearchFetcher.expire()
    fetcher.search("FRPAR", "FRMRS", TRAVEL_DATE)
    assert len(query_counter) > queries_after_first
