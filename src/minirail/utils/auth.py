from typing import Annotated

from fastapi import Depends, Header, Response
from sqlalchemy.orm import Session

from minirail.sales.fetcher.sales_channel import SalesChannelFetcher
from minirail.sales.schemas.sales_channel import SalesChannelSchema
from minirail.utils.api import session_transaction
from minirail.utils.exc import InvalidAPIKeyException
from minirail.utils.rate_limit import apply_soft_rate_limit


def get_current_sales_channel(
    response: Response,
    session: Annotated[Session, Depends(session_transaction)],
    x_api_key: Annotated[str | None, Header()] = None,
) -> SalesChannelSchema:
    """Authenticate the caller from the X-API-Key header.

    After a successful lookup, applies the soft per-channel rate limit
    (headers only — never blocks the request).
    """
    if x_api_key is None:
        raise InvalidAPIKeyException("Missing X-API-Key header")
    channel = SalesChannelFetcher(session).get_by_api_key(x_api_key)
    if channel is None or not channel.is_active:
        raise InvalidAPIKeyException("Unknown or inactive API key")
    apply_soft_rate_limit(channel.id, response)
    return channel


CurrentSalesChannel = Annotated[SalesChannelSchema, Depends(get_current_sales_channel)]
