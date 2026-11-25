"""Soft per-sales-channel rate limiting.

Over-limit requests are still served: the quota is advisory. Callers see
`X-RateLimit-*` headers; when exceeded we also set `X-RateLimit-Soft-Exceeded`
and log a warning. Hard 429 rejection is intentionally out of scope.
"""

from fastapi import Response

from minirail.utils.app import get_app
from minirail.utils.redis import REDIS_CONNECTION_EXCEPTIONS

RATE_LIMIT_PREFIX = "minirail-ratelimit"
WINDOW_SECONDS = 60


def apply_soft_rate_limit(sales_channel_id: int, response: Response) -> None:
    """Increment the channel's rolling-minute counter and annotate the response.

    Redis failures are swallowed: a soft limiter must not turn a Redis blip
    into a failed authenticated request (auth cache already 503s on outage
    for cache reads/writes; this path is best-effort).
    """
    limit = get_app().configuration.api.rate_limit_per_minute
    if limit <= 0:
        return

    redis = get_app().redis
    key = f"{RATE_LIMIT_PREFIX}::{sales_channel_id}"
    try:
        raw = redis.get(key)
        count = int(raw.decode()) + 1 if raw is not None else 1
        redis.set(key, str(count).encode(), ex=WINDOW_SECONDS)
    except REDIS_CONNECTION_EXCEPTIONS:
        get_app().logger.warning(
            "Soft rate limit skipped: Redis unavailable (sales_channel_id=%s)",
            sales_channel_id,
        )
        return
    except ValueError, UnicodeDecodeError:
        # Corrupt counter — reset rather than fail the request.
        redis.set(key, b"1", ex=WINDOW_SECONDS)
        count = 1

    remaining = max(0, limit - count)
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    if count > limit:
        response.headers["X-RateLimit-Soft-Exceeded"] = "1"
        get_app().logger.warning(
            "Soft rate limit exceeded for sales_channel_id=%s count=%s limit=%s",
            sales_channel_id,
            count,
            limit,
        )
