from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from minirail.inventory.models import OD, Station
from minirail.sales.jobs.create_booking import CreateBookingJob
from minirail.sales.models import Booking, BookingExpiryOutbox, SalesChannel
from minirail.sales.schemas.booking import PassengerInputSchema
from minirail.sales.service.outbox import drain_booking_expiry_outbox
from minirail.utils.app import get_app
from tests.factories import SalesChannelFactory
from tests.helpers import build_service_with_ods
from tests.sales.conftest import create_booking_via_api


def test_create_booking_writes_and_drains_expiry_outbox(
    client: TestClient,
    auth_headers: dict[str, str],
    session: Session,
    paris_marseille_od: OD,
    sent_messages: list[tuple[Any, int | None]],
) -> None:
    body = create_booking_via_api(client, auth_headers, session, paris_marseille_od.id, passenger_count=1)
    booking = session.scalars(select(Booking).where(Booking.booking_key == body["bookingKey"])).one()

    outbox = session.scalars(select(BookingExpiryOutbox).where(BookingExpiryOutbox.booking_id == booking.id)).one()
    assert outbox.delay_ms == get_app().configuration.api.booking_ttl_seconds * 1000
    assert outbox.published_at is not None

    expiry_messages = [(m, delay) for m, delay in sent_messages if m.actor_name == "expire_booking"]
    assert len(expiry_messages) == 1
    assert expiry_messages[0][0].args == (booking.id,)


def test_drain_is_idempotent_once_published(
    client: TestClient,
    auth_headers: dict[str, str],
    session: Session,
    paris_marseille_od: OD,
    sent_messages: list[tuple[Any, int | None]],
) -> None:
    create_booking_via_api(client, auth_headers, session, paris_marseille_od.id, passenger_count=1)
    before = len([m for m, _ in sent_messages if m.actor_name == "expire_booking"])

    published = drain_booking_expiry_outbox(session)
    session.flush()

    assert published == 0
    after = len([m for m, _ in sent_messages if m.actor_name == "expire_booking"])
    assert after == before


def test_outbox_stays_unpublished_until_drain(session: Session) -> None:
    """Simulates the gap after commit-before-drain: intent is durable, broker silent."""
    channel = cast(SalesChannel, SalesChannelFactory())
    service = build_service_with_ods(session, station_codes=["FRAAA", "FRBBB"])
    origin = session.scalars(select(Station).where(Station.code == "FRAAA")).one()
    destination = session.scalars(select(Station).where(Station.code == "FRBBB")).one()
    od = session.scalars(
        select(OD).where(
            OD.service_id == service.id,
            OD.origin_station_id == origin.id,
            OD.destination_station_id == destination.id,
        )
    ).one()

    booking = CreateBookingJob(
        session=session,
        sales_channel_id=channel.id,
        od_id=od.id,
        passengers=[PassengerInputSchema(first_name="Ada", last_name="Lovelace")],
    ).call_for_api()

    outbox = session.scalars(select(BookingExpiryOutbox).where(BookingExpiryOutbox.booking_id == booking.id)).one()
    assert outbox.published_at is None

    assert drain_booking_expiry_outbox(session) == 1
    session.refresh(outbox)
    assert outbox.published_at is not None
