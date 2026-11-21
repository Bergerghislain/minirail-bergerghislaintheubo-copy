from datetime import UTC, datetime


def utc_now() -> datetime:
    """The one true clock: always timezone-aware, always UTC."""
    return datetime.now(tz=UTC)
