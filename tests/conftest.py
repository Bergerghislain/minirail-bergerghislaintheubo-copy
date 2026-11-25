"""Test harness.

Two ideas matter here:

1. **A dedicated test database**, recreated once per test run, with the schema
   built straight from the model metadata (the alembic chain is validated
   separately, in CI's `migrations` job).

2. **Transaction-as-you-go isolation**: each test runs inside one outer
   database transaction that is rolled back at teardown. The application's
   session factory is patched to hand out sessions bound to that same
   connection (committing only releases a savepoint), so application code can
   `commit()` freely and the test still leaves no trace.
"""

from collections.abc import Generator, Iterator
from fnmatch import fnmatch
from typing import Any, override

import pytest
import remoulade
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError
from remoulade.brokers.stub import StubBroker
from remoulade.middleware import Middleware
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from minirail.asgi import create_asgi_app
from minirail.orm import Base
from minirail.utils.app import App, create_app, set_app
from minirail.utils.config import Configuration, load_configuration

TEST_DATABASE_NAME = "minirail_test"


def _build_test_configuration() -> Configuration:
    configuration = load_configuration()
    raw = configuration.model_dump()
    base_dsn, _, _ = configuration.database.dsn.rpartition("/")
    raw["database"]["dsn"] = f"{base_dsn}/{TEST_DATABASE_NAME}"
    return Configuration.model_validate(raw)


@pytest.fixture(scope="session")
def test_app() -> Generator[App]:
    # (Re)create the test database using the configured database as admin entrypoint.
    admin_engine = create_engine(load_configuration().database.dsn, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.execute(text(f"DROP DATABASE IF EXISTS {TEST_DATABASE_NAME} WITH (FORCE)"))
        connection.execute(text(f"CREATE DATABASE {TEST_DATABASE_NAME}"))
    admin_engine.dispose()

    app = create_app(_build_test_configuration())
    Base.metadata.create_all(app.engine)
    set_app(app)
    yield app
    set_app(None)
    app.engine.dispose()


@pytest.fixture(autouse=True)
def session(test_app: App) -> Generator[Session]:
    """The test's database session, isolated by an outer rolled-back transaction.

    Application code reaching the database through get_app().session_factory
    joins the same connection via savepoints, so everything any layer writes
    during the test is visible to this session — and gone after it.
    """
    connection = test_app.engine.connect()
    outer_transaction = connection.begin()
    test_factory = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
    original_factory = test_app.session_factory
    test_app.session_factory = test_factory
    test_session = test_factory()
    yield test_session
    test_session.close()
    test_app.session_factory = original_factory
    outer_transaction.rollback()
    connection.close()


class FakeRedis:
    """In-memory stand-in implementing the RedisClient protocol.

    `break_connection()` makes every subsequent call raise, to test how the
    application behaves during a Redis outage.
    """

    def __init__(self) -> None:
        self.storage: dict[str, bytes] = {}
        self._broken = False

    def break_connection(self) -> None:
        self._broken = True

    def _check(self) -> None:
        if self._broken:
            raise RedisConnectionError("fake redis: connection refused")

    @staticmethod
    def _as_str(name: str | bytes) -> str:
        return name.decode() if isinstance(name, bytes) else name

    def get(self, name: str) -> bytes | None:
        self._check()
        return self.storage.get(name)

    def set(self, name: str, value: bytes, ex: int | None = None) -> bool | None:
        self._check()
        self.storage[name] = value
        return True

    def incr(self, name: str) -> int:
        self._check()
        key = self._as_str(name)
        current = int(self.storage.get(key, b"0"))
        current += 1
        self.storage[key] = str(current).encode()
        return current

    def expire(self, name: str, time: int) -> bool:
        self._check()
        # TTL is not simulated; presence alone is enough for tests.
        return self._as_str(name) in self.storage

    def delete(self, *names: str | bytes) -> int:
        self._check()
        return sum(1 for name in names if self.storage.pop(self._as_str(name), None) is not None)

    def scan_iter(self, match: str, count: int) -> Iterator[bytes]:
        self._check()
        for key in list(self.storage):
            if fnmatch(key, match):
                yield key.encode()

    def ping(self) -> bool:
        self._check()
        return True


@pytest.fixture(autouse=True)
def fake_redis(test_app: App) -> Generator[FakeRedis]:
    original = test_app.redis
    fake = FakeRedis()
    test_app.redis = fake
    yield fake
    test_app.redis = original


@pytest.fixture(autouse=True)
def _bind_factories(session: Session) -> None:
    from tests.factories import ALL_FACTORIES

    for factory_class in ALL_FACTORIES:
        factory_class._meta.sqlalchemy_session = session


class _EnqueueRecorder(Middleware):
    """Records every enqueued message so tests can assert on background work
    without running a worker."""

    def __init__(self) -> None:
        self.messages: list[tuple[Any, int | None]] = []

    @override
    def after_enqueue(self, broker: Any, message: Any, delay: int | None, exception: Any = None) -> None:
        self.messages.append((message, delay))


_enqueue_recorder = _EnqueueRecorder()


@pytest.fixture(scope="session")
def stub_broker() -> StubBroker:
    """A broker that queues messages without executing them.

    Deliberately NOT remoulade's LocalBroker, which runs actors inline on
    enqueue: the delayed expiry message would expire every booking the moment
    it is created.
    """
    broker = StubBroker()
    broker.add_middleware(_enqueue_recorder)
    remoulade.set_broker(broker)

    from minirail.sales.actors.booking_expiry import expire_booking
    from minirail.sales.actors.notifications import send_booking_notification

    remoulade.declare_actors([expire_booking, send_booking_notification])
    return broker


@pytest.fixture(autouse=True)
def sent_messages(stub_broker: StubBroker) -> list[tuple[Any, int | None]]:
    _enqueue_recorder.messages.clear()
    return _enqueue_recorder.messages


@pytest.fixture(scope="session")
def client(test_app: App, stub_broker: StubBroker) -> Generator[TestClient]:
    with TestClient(create_asgi_app()) as test_client:
        yield test_client


@pytest.fixture
def auth_headers(session: Session) -> dict[str, str]:
    """Headers of a freshly created, active sales channel."""
    from tests.factories import SalesChannelFactory

    channel = SalesChannelFactory()
    return {"X-API-Key": channel.api_key}


@pytest.fixture
def query_counter(test_app: App) -> Generator[list[str]]:
    """Collects every SQL statement executed during the test (cache-hit proofs)."""
    from sqlalchemy import event

    statements: list[str] = []

    def _record(conn: object, cursor: object, statement: str, *args: object) -> None:
        statements.append(statement)

    event.listen(test_app.engine, "before_cursor_execute", _record)
    yield statements
    event.remove(test_app.engine, "before_cursor_execute", _record)
