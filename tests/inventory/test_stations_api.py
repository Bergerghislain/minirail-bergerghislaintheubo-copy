from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import StationFactory


def test_list_stations_camel_case_payload(client: TestClient, auth_headers: dict[str, str], session: Session) -> None:
    StationFactory(code="FRPAR", name="Paris Gare de Lyon", timezone="Europe/Paris")
    StationFactory(code="FRMRS", name="Marseille Saint-Charles", timezone="Europe/Paris")

    response = client.get("/api/stations/", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == [
        {"code": "FRMRS", "name": "Marseille Saint-Charles", "timezone": "Europe/Paris"},
        {"code": "FRPAR", "name": "Paris Gare de Lyon", "timezone": "Europe/Paris"},
    ]
