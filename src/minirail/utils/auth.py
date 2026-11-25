from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from minirail.sales.fetcher.sales_channel import SalesChannelFetcher
from minirail.sales.schemas.sales_channel import SalesChannelSchema
from minirail.utils.api import session_transaction
from minirail.utils.exc import InvalidAPIKeyException
from minirail.utils.rate_limit import enforce_rate_limit


def get_current_sales_channel(
    session: Annotated[Session, Depends(session_transaction)],
    x_api_key: Annotated[str | None, Header()] = None,
) -> SalesChannelSchema:
    """Authenticate the caller from the X-API-Key header."""
    if x_api_key is None:
        raise InvalidAPIKeyException("Missing X-API-Key header")
    channel = SalesChannelFetcher(session).get_by_api_key(x_api_key)
    if channel is None or not channel.is_active:
        raise InvalidAPIKeyException("Unknown or inactive API key")
    enforce_rate_limit(sales_channel_id=channel.id)
    return channel


CurrentSalesChannel = Annotated[SalesChannelSchema, Depends(get_current_sales_channel)]
