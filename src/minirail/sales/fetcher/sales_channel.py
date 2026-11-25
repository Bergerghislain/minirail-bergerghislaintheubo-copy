from typing import ClassVar, override

from sqlalchemy import select

from minirail.sales.models import SalesChannel
from minirail.sales.schemas.sales_channel import SalesChannelSchema
from minirail.utils.app import get_app
from minirail.utils.fetcher import SQLOneFetcher


class SalesChannelFetcher(SQLOneFetcher[SalesChannelSchema]):
    """Authentication hot path: looked up on every request, so cached.

    The TTL (from `api.auth_cache_ttl_seconds`) bounds how long a deactivated
    channel keeps working (and a reactivated one stays shut out). Writes that
    change a channel should call SalesChannelFetcher.expire() to make the
    change immediate.
    """

    cache_enabled: ClassVar[bool] = True
    # Fallback only; runtime TTL comes from configuration via _cache_ttl_seconds.
    cache_ttl_seconds: ClassVar[int] = 60

    @property
    @override
    def output_schema(self) -> type[SalesChannelSchema]:
        return SalesChannelSchema

    @override
    def _cache_ttl_seconds(self) -> int:
        return get_app().configuration.api.auth_cache_ttl_seconds

    @override
    def _fetch_one(self, identifier: str) -> SalesChannelSchema | None:
        channel = self.session.scalars(select(SalesChannel).where(SalesChannel.api_key == identifier)).one_or_none()
        return SalesChannelSchema.model_validate(channel) if channel is not None else None

    def get_by_api_key(self, api_key: str) -> SalesChannelSchema | None:
        return self.get_one(api_key)
