from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import SalesChannelFactory


def test_missing_api_key_is_401(client: TestClient) -> None:
    response = client.get("/api/stations/")
    assert response.status_code == 401
    assert response.json() == {"errorCode": "invalid_api_key", "message": "Missing X-API-Key header"}


def test_unknown_api_key_is_401(client: TestClient) -> None:
    response = client.get("/api/stations/", headers={"X-API-Key": "nope"})
    assert response.status_code == 401
    assert response.json()["errorCode"] == "invalid_api_key"


def test_inactive_channel_is_401(client: TestClient, session: Session) -> None:
    channel = SalesChannelFactory(is_active=False)
    response = client.get("/api/stations/", headers={"X-API-Key": channel.api_key})
    assert response.status_code == 401


def test_active_channel_is_accepted(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/api/stations/", headers=auth_headers)
    assert response.status_code == 200
