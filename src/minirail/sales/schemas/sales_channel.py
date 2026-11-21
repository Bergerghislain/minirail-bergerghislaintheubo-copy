from minirail.utils.schema import Schema


class SalesChannelSchema(Schema):
    """Internal representation of the authenticated caller. Never exposes the API key."""

    id: int
    name: str
    is_active: bool
