"""Booking endpoints.

The endpoint owns the unit of work: it runs a job, commits once, and only
then triggers side effects (enqueue background messages, invalidate caches).
Side effects before the commit would reference state that might roll back.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from minirail.inventory.fetcher.trip_search import TripSearchFetcher
from minirail.sales.actors.booking_expiry import expire_booking
from minirail.sales.actors.notifications import send_booking_notification
from minirail.sales.fetcher.booking import BookingFetcher
from minirail.sales.jobs.cancel_booking import CancelBookingJob
from minirail.sales.jobs.confirm_booking import ConfirmBookingJob
from minirail.sales.jobs.create_booking import CreateBookingJob
from minirail.sales.schemas.booking import BookingConfirmSchema, BookingCreateSchema, BookingOutputSchema
from minirail.utils.api import session_transaction
from minirail.utils.app import get_app
from minirail.utils.auth import CurrentSalesChannel

router = APIRouter(prefix="/api/bookings", tags=["sales"])


@router.post("/", status_code=201)
def create_booking(
    sales_channel: CurrentSalesChannel,
    session: Annotated[Session, Depends(session_transaction)],
    payload: BookingCreateSchema,
) -> BookingOutputSchema:
    booking = CreateBookingJob(
        session=session,
        sales_channel_id=sales_channel.id,
        od_id=payload.od_id,
        passengers=payload.passengers,
        discount_code=payload.discount_code,
    ).call_for_api()
    session.commit()

    ttl_ms = get_app().configuration.api.booking_ttl_seconds * 1000
    expire_booking.send_with_options(args=(booking.id,), delay=ttl_ms)
    TripSearchFetcher.expire()
    return BookingFetcher(session).get_by_key_or_raise(booking.booking_key)


@router.get("/{booking_key}")
def get_booking(
    sales_channel: CurrentSalesChannel,
    session: Annotated[Session, Depends(session_transaction)],
    booking_key: str,
) -> BookingOutputSchema:
    return BookingFetcher(session).get_by_key_or_raise(booking_key)


@router.post("/{booking_key}/confirm")
def confirm_booking(
    sales_channel: CurrentSalesChannel,
    session: Annotated[Session, Depends(session_transaction)],
    booking_key: str,
    payload: BookingConfirmSchema,
) -> BookingOutputSchema:
    booking = ConfirmBookingJob(
        session=session,
        booking_key=booking_key,
        payment_token=payload.payment_token,
    ).call_for_api()
    session.commit()

    send_booking_notification.send(booking.id, "booking.confirmed")
    return BookingFetcher(session).get_by_key_or_raise(booking_key)


@router.post("/{booking_key}/cancel")
def cancel_booking(
    sales_channel: CurrentSalesChannel,
    session: Annotated[Session, Depends(session_transaction)],
    booking_key: str,
) -> BookingOutputSchema:
    booking = CancelBookingJob(session=session, booking_key=booking_key).call_for_api()
    session.commit()

    send_booking_notification.send(booking.id, "booking.cancelled")
    TripSearchFetcher.expire()  # seats came back
    return BookingFetcher(session).get_by_key_or_raise(booking_key)
