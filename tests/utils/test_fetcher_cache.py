from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from minirail.inventory.fetcher.station import StationFetcher
from tests.conftest import FakeRedis
from tests.factories import StationFactory


def test_cache_hit_skips_the_database(session: Session, query_counter: list[str]) -> None:
    StationFactory(code="FRAAA")
    fetcher = StationFetcher(session)

    first = fetcher.get_all()
    queries_after_first = len(query_counter)
    second = fetcher.get_all()

    assert first == second
    assert len(query_counter) == queries_after_first, "second call must be served from cache"


def test_cached_value_is_stale_until_expired(session: Session) -> None:
    station = StationFactory(code="FRAAA", name="Old Name")
    fetcher = StationFetcher(session)
    assert fetcher.get_one("FRAAA") is not None

    station.name = "New Name"
    session.flush()

    cached = fetcher.get_one("FRAAA")
    assert cached is not None
    assert cached.name == "Old Name", "the write did not invalidate, so the cache is stale"

    StationFetcher.expire()
    fresh = fetcher.get_one("FRAAA")
    assert fresh is not None
    assert fresh.name == "New Name"


def test_expire_only_touches_its_own_group(session: Session, fake_redis: FakeRedis) -> None:
    fake_redis.set("minirail-cache::SomeOtherFetcher::x", b"untouched")
    StationFactory(code="FRAAA")
    StationFetcher(session).get_all()

    StationFetcher.expire()

    assert fake_redis.get("minirail-cache::SomeOtherFetcher::x") == b"untouched"
    assert not [key for key in fake_redis.storage if "StationFetcher" in key]


def test_redis_outage_is_a_503(client: TestClient, auth_headers: dict[str, str], fake_redis: FakeRedis) -> None:
    """A cached read path fails loudly during an outage instead of silently
    bypassing the cache (see minirail/utils/fetcher.py for the rationale)."""
    fake_redis.break_connection()
    response = client.get("/api/stations/", headers=auth_headers)
    # Even authentication goes through a cached fetcher, so the 503 hits first.
    assert response.status_code == 503
    assert response.json()["errorCode"] == "service_unavailable"
