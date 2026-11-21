import logging
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol, cast

import redis
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from minirail.utils.config import Configuration, load_configuration


class RedisClient(Protocol):
    """The subset of the redis client this application uses, fully typed.

    redis-py's own annotations are too loose for strict type checking; going
    through this protocol also keeps the cache surface small and auditable.
    """

    def get(self, name: str) -> bytes | None: ...
    def set(self, name: str, value: bytes, ex: int | None = None) -> bool | None: ...
    def delete(self, *names: str | bytes) -> int: ...
    def scan_iter(self, match: str, count: int) -> Iterator[bytes]: ...
    def ping(self) -> bool: ...


@dataclass
class App:
    """Process-wide application context: configuration and connections.

    Built once per process (API, worker, CLI) and reached through get_app().
    """

    configuration: Configuration
    engine: Engine
    session_factory: sessionmaker[Session]
    redis: RedisClient
    logger: logging.Logger


_app: App | None = None


def create_app(configuration: Configuration | None = None) -> App:
    if configuration is None:
        configuration = load_configuration()
    engine = create_engine(configuration.database.dsn, pool_pre_ping=True)
    redis_client = cast("RedisClient", redis.Redis.from_url(configuration.redis.dsn))  # pyright: ignore[reportUnknownMemberType]
    return App(
        configuration=configuration,
        engine=engine,
        session_factory=sessionmaker(bind=engine),
        redis=redis_client,
        logger=logging.getLogger("minirail"),
    )


def get_app() -> App:
    global _app
    if _app is None:
        _app = create_app()
    return _app


def set_app(app: App | None) -> None:
    """Replace the process-wide App (used by tests)."""
    global _app
    _app = app


@contextmanager
def get_session(session: Session | None = None) -> Generator[Session]:
    """Yield a database session, reusing the caller's if provided.

    Reuse is what makes jobs and services composable: a job called with an
    existing session participates in the caller's transaction instead of
    opening its own. When this function does create the session, it rolls
    back on error and closes it — but it NEVER commits. Committing is the
    caller's decision, and it belongs to the api/actor/cli layer.
    """
    if session is not None:
        yield session
        return
    new_session = get_app().session_factory()
    try:
        yield new_session
        new_session.rollback()  # discard anything the caller forgot; commits must be explicit
    except Exception:
        new_session.rollback()
        raise
    finally:
        new_session.close()
