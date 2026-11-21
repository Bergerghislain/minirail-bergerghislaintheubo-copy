from datetime import UTC, datetime
from typing import Any, override

from sqlalchemy import DateTime, MetaData
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.types import TypeDecorator

# Deterministic constraint names: without these, PostgreSQL generates its own
# names and alembic autogenerate produces noisy, un-reproducible migrations.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# Alias used in signatures across the codebase; keeps the door open to a
# custom Session subclass without touching every annotation.
type MinirailSession = Session


class UTCDateTime(TypeDecorator[datetime]):
    """A timestamp column that only accepts timezone-aware datetimes.

    Values are normalized to UTC before storage and always come back
    timezone-aware. Passing a naive datetime is a programming error and
    raises immediately instead of storing an ambiguous value.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    @override
    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("UTCDateTime columns refuse naive datetimes; use minirail.utils.date_utils.utc_now()")
        return value.astimezone(UTC)

    @override
    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError(f"Expected datetime from the database, got {type(value)!r}")
        return value.astimezone(UTC)
