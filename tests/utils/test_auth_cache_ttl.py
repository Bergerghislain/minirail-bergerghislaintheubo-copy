from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from minirail.sales.fetcher.sales_channel import SalesChannelFetcher
from minirail.utils.app import get_app
from tests.conftest import FakeRedis
from tests.factories import SalesChannelFactory


def test_auth_cache_ttl_comes_from_config(session: Session, fake_redis: FakeRedis) -> None:
    channel = SalesChannelFactory()
    original = get_app().configuration.api.auth_cache_ttl_seconds
    get_app().configuration.api.auth_cache_ttl_seconds = 42
    spy = MagicMock(wraps=fake_redis.set)
    fake_redis.set = spy  # type: ignore[method-assign]
    try:
        SalesChannelFetcher.expire()
        SalesChannelFetcher(session).get_by_api_key(channel.api_key)
        assert spy.called
        assert spy.call_args.kwargs["ex"] == 42
    finally:
        get_app().configuration.api.auth_cache_ttl_seconds = original
