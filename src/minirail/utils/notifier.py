"""Outbound notifications to sales channels.

In production this would POST to each channel's webhook URL; the demo logs a
structured line instead so the project runs offline. Called from actors, not
from request handlers: a slow or failing partner endpoint must never hold up
an API response (or a database transaction).
"""

from typing import Any

from minirail.utils.app import get_app


def notify(sales_channel_name: str, event: str, payload: dict[str, Any]) -> None:
    get_app().logger.info("webhook -> channel=%s event=%s payload=%s", sales_channel_name, event, payload)
