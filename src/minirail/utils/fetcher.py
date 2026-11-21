"""Read-side query objects.

A fetcher owns one family of read queries and returns Pydantic schemas, never
ORM objects: callers get plain, serializable data with no live session
attached. Fetchers may opt into Redis caching by flipping `cache_enabled`;
entries are grouped per fetcher class so a whole family can be invalidated at
once with `SomeFetcher.expire()`.

During a Redis outage, cached fetchers fail with a 503 rather than silently
serving straight from the database: a response that skips the cache is cheap,
but writes that skip cache *invalidation* would leave stale entries behind —
refusing loudly keeps the failure visible and symmetric.
"""

from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import TypeAdapter

from minirail.orm import MinirailSession
from minirail.utils.app import get_app
from minirail.utils.exc import ItemNotFoundException
from minirail.utils.redis import cache_key, expire_cache, handle_redis_connection_error
from minirail.utils.schema import Schema


class SQLBaseFetcher[OutputT: Schema](ABC):
    cache_enabled: ClassVar[bool] = False
    cache_ttl_seconds: ClassVar[int] = 60

    def __init__(self, session: MinirailSession) -> None:
        self.session = session

    @property
    @abstractmethod
    def output_schema(self) -> type[OutputT]: ...

    @classmethod
    def cache_group(cls) -> str:
        return cls.__name__

    @classmethod
    def expire(cls) -> None:
        """Invalidate every cached entry of this fetcher. Call after any write
        that changes what this fetcher returns."""
        expire_cache(cls.cache_group())

    # -- caching helpers ----------------------------------------------------

    @handle_redis_connection_error
    def _cache_read(self, identifier: str) -> bytes | None:
        if not self.cache_enabled:
            return None
        return get_app().redis.get(cache_key(self.cache_group(), identifier))

    @handle_redis_connection_error
    def _cache_write(self, identifier: str, payload: bytes) -> None:
        if not self.cache_enabled:
            return
        get_app().redis.set(cache_key(self.cache_group(), identifier), payload, ex=self.cache_ttl_seconds)

    def _cached_one(self, identifier: str) -> OutputT | None:
        payload = self._cache_read(identifier)
        if payload is None:
            return None
        return self.output_schema.model_validate_json(payload)

    def _cached_list(self, identifier: str) -> list[OutputT] | None:
        payload = self._cache_read(identifier)
        if payload is None:
            return None
        return TypeAdapter(list[self.output_schema]).validate_json(payload)  # pyright: ignore[reportInvalidTypeArguments]

    def _store_one(self, identifier: str, item: OutputT) -> None:
        self._cache_write(identifier, item.model_dump_json().encode())

    def _store_list(self, identifier: str, items: list[OutputT]) -> None:
        payload = TypeAdapter(list[self.output_schema]).dump_json(items)  # pyright: ignore[reportInvalidTypeArguments]
        self._cache_write(identifier, payload)


class SQLOneFetcher[OutputT: Schema](SQLBaseFetcher[OutputT]):
    """Fetcher retrieving a single item by a string identifier."""

    @abstractmethod
    def _fetch_one(self, identifier: str) -> OutputT | None: ...

    def get_one(self, identifier: str) -> OutputT | None:
        cached = self._cached_one(identifier)
        if cached is not None:
            return cached
        item = self._fetch_one(identifier)
        if item is not None:
            self._store_one(identifier, item)
        return item

    def get_one_or_raise(self, identifier: str) -> OutputT:
        item = self.get_one(identifier)
        if item is None:
            raise ItemNotFoundException(
                f"{self.output_schema.__name__.removesuffix('Schema')} {identifier!r} not found"
            )
        return item
