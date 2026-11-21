"""Remoulade broker wiring.

The task queue rides on PostgreSQL (no extra infrastructure locally): the
broker keeps its queue tables in a dedicated `remoulade` schema of the
configured database. Call init_broker() once per process — both the API
(which enqueues) and the worker (which consumes) need it.
"""

import remoulade
from remoulade.brokers.postgres import PostgresBroker

from minirail.utils.app import get_app


def init_broker(broker: remoulade.Broker | None = None) -> None:
    if broker is None:
        broker = PostgresBroker(url=get_app().configuration.broker.url)
    remoulade.set_broker(broker)

    # Imported here (not at module top) because actor modules need a broker to
    # exist by the time declare_actors runs, and to avoid import cycles.
    from minirail.sales.actors.booking_expiry import expire_booking
    from minirail.sales.actors.notifications import send_booking_notification

    remoulade.declare_actors([expire_booking, send_booking_notification])  # pyright: ignore[reportUnknownMemberType]
