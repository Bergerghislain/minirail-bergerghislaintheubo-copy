from collections.abc import Callable
from functools import wraps

from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from minirail.utils.app import get_app
from minirail.utils.exc import ServiceUnavailableException

REDIS_CONNECTION_EXCEPTIONS = (RedisConnectionError, RedisTimeoutError)

# Every cache key in the application lives under this prefix, namespaced as
# f"{CACHE_PREFIX}::<group>::<identifier>".
CACHE_PREFIX = "minirail-cache"


def cache_key(group: str, identifier: str) -> str:
    return f"{CACHE_PREFIX}::{group}::{identifier}"


def handle_redis_connection_error[**P, T](func: Callable[P, T]) -> Callable[P, T]:
    """Translate a Redis outage into a clean 503 instead of a 500.

    A stale cache would be worse than a refused request: callers must not
    silently proceed as if the cache layer were consistent.
    """

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return func(*args, **kwargs)
        except REDIS_CONNECTION_EXCEPTIONS as exc:
            raise ServiceUnavailableException("Redis is unavailable") from exc

    return wrapper


@handle_redis_connection_error
def expire_cache(group: str) -> int:
    """Delete every cache entry in a group. Returns the number of keys deleted.

    Uses SCAN, never KEYS: KEYS is O(N) over the whole keyspace and blocks
    the Redis event loop, which stalls every other client sharing the server.
    """
    client = get_app().redis
    pattern = f"{CACHE_PREFIX}::{group}::*"
    deleted = 0
    batch: list[bytes] = []
    for key in client.scan_iter(match=pattern, count=500):
        batch.append(key)
        if len(batch) >= 500:
            deleted += int(client.delete(*batch))
            batch = []
    if batch:
        deleted += int(client.delete(*batch))
    return deleted
