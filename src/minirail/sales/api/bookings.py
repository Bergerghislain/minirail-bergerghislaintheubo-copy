"""Booking endpoints.

The endpoint owns the unit of work: it runs a job, commits once, and only
then triggers side effects (enqueue background messages, invalidate caches).
Side effects before the commit would reference state that might roll back.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy.orm import Session

from minirail.inventory.fetcher.trip_search import TripSearchFetcher
from minirail.sales.actors.notifications import send_booking_notification
from minirail.sales.fetcher.booking import BookingFetcher
from minirail.sales.jobs.cancel_booking import CancelBookingJob
from minirail.sales.jobs.confirm_booking import ConfirmBookingJob
from minirail.sales.jobs.create_booking import CreateBookingJob
from minirail.sales.models import Booking
from minirail.sales.schemas.booking import BookingConfirmSchema, BookingCreateSchema, BookingOutputSchema
from minirail.sales.service.idempotency import (
    fingerprint_booking_create,
    resolve_booking_idempotency,
    store_booking_idempotency,
)
from minirail.sales.service.outbox import drain_booking_expiry_outbox
from minirail.utils.api import session_transaction
from minirail.utils.auth import CurrentSalesChannel

router = APIRouter(prefix="/api/bookings", tags=["sales"])


@router.post("/", status_code=201)
def create_booking(
    sales_channel: CurrentSalesChannel,
    session: Annotated[Session, Depends(session_transaction)],
    payload: BookingCreateSchema,
    response: Response,
    idempotency_key: Annotated[str | None, Header()] = None,
) -> BookingOutputSchema:
    key = idempotency_key.strip() if idempotency_key is not None else ""
    request_hash = fingerprint_booking_create(payload) if key else None

    if key and request_hash is not None:
        existing = resolve_booking_idempotency(
            session,
            sales_channel_id=sales_channel.id,
            key=key,
            request_hash=request_hash,
        )
        if existing is not None:
            # Replay: same booking, no new side effects (expiry enqueue / cache bust).
            response.status_code = 200
            booking = session.get_one(Booking, existing.booking_id)
            return BookingFetcher(session).get_by_key_or_raise(booking.booking_key)

    booking = CreateBookingJob(
        session=session,
        sales_channel_id=sales_channel.id,
        od_id=payload.od_id,
        passengers=payload.passengers,
        discount_code=payload.discount_code,
    ).call_for_api()
    if key and request_hash is not None:
        store_booking_idempotency(
            session,
            sales_channel_id=sales_channel.id,
            key=key,
            request_hash=request_hash,
            booking_id=booking.id,
        )
    # Booking + outbox row commit together; then drain publishes to remoulade.
    session.commit()
    drain_booking_expiry_outbox(session)
    session.commit()
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
