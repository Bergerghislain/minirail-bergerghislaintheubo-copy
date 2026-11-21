import remoulade
from sqlalchemy import select

import minirail.utils.notifier
from minirail.sales.models import Booking
from minirail.utils.app import get_session


@remoulade.actor
def send_booking_notification(booking_id: int, event: str) -> None:
    """Tell the sales channel about a booking lifecycle event.

    Runs on the worker so a slow partner endpoint never delays an API
    response; enqueued only after the triggering transaction committed.
    """
    with get_session() as session:
        booking = session.scalars(select(Booking).where(Booking.id == booking_id)).one_or_none()
        if booking is None:
            return
        minirail.utils.notifier.notify(
            booking.sales_channel.name,
            event,
            {"bookingKey": booking.booking_key, "pnr": booking.pnr, "status": booking.status},
        )
