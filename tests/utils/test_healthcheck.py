from fastapi.testclient import TestClient

from tests.conftest import FakeRedis


def test_ping(client: TestClient) -> None:
    response = client.get("/api/healthcheck/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_deep_check_all_services_up(client: TestClient) -> None:
    response = client.get("/api/healthcheck/deep")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "services": {"postgres": "ok", "redis": "ok"}}


def test_deep_check_redis_down_returns_503(client: TestClient, fake_redis: FakeRedis) -> None:
    fake_redis.break_connection()
    response = client.get("/api/healthcheck/deep")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["services"]["redis"] == "unreachable"
    assert body["services"]["postgres"] == "ok"
