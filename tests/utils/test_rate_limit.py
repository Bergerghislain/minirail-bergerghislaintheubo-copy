from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from minirail.utils.app import get_app
from tests.factories import SalesChannelFactory


def test_soft_rate_limit_headers_under_quota(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/api/stations/", headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == str(get_app().configuration.api.rate_limit_per_minute)
    assert int(response.headers["X-RateLimit-Remaining"]) >= 0
    assert "X-RateLimit-Soft-Exceeded" not in response.headers


def test_soft_rate_limit_exceeded_still_serves(client: TestClient, session: Session) -> None:
    channel = SalesChannelFactory()
    headers = {"X-API-Key": channel.api_key}
    original = get_app().configuration.api.rate_limit_per_minute
    get_app().configuration.api.rate_limit_per_minute = 1
    try:
        first = client.get("/api/stations/", headers=headers)
        assert first.status_code == 200
        assert "X-RateLimit-Soft-Exceeded" not in first.headers

        second = client.get("/api/stations/", headers=headers)
        assert second.status_code == 200  # soft: still served
        assert second.headers["X-RateLimit-Soft-Exceeded"] == "1"
        assert second.headers["X-RateLimit-Remaining"] == "0"
    finally:
        get_app().configuration.api.rate_limit_per_minute = original


def test_soft_rate_limit_disabled(client: TestClient, auth_headers: dict[str, str]) -> None:
    original = get_app().configuration.api.rate_limit_per_minute
    get_app().configuration.api.rate_limit_per_minute = 0
    try:
        response = client.get("/api/stations/", headers=auth_headers)
        assert response.status_code == 200
        assert "X-RateLimit-Limit" not in response.headers
    finally:
        get_app().configuration.api.rate_limit_per_minute = original
