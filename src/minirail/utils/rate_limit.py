"""Per-sales-channel request rate limiting backed by Redis."""

from minirail.utils.app import get_app
from minirail.utils.exc import RateLimitedException
from minirail.utils.redis import handle_redis_connection_error


@handle_redis_connection_error
def enforce_rate_limit(*, sales_channel_id: int) -> None:
    """Increment a one-minute window counter; raise when over the configured cap."""
    app = get_app()
    limit = app.configuration.api.rate_limit_per_minute
    if limit <= 0:
        return
    key = f"minirail-ratelimit::{sales_channel_id}"
    client = app.redis
    # FakeRedis and redis-py both expose incr; expire only on the first hit.
    count = int(client.incr(key))
    if count == 1:
        client.expire(key, 60)
    if count > limit:
        raise RateLimitedException(f"Rate limit of {limit} requests per minute exceeded")
