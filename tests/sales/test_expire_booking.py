from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from minirail.inventory.models import OD, Leg
from minirail.sales.jobs.expire_booking import ExpireBookingJob, find_stale_booking_ids
from minirail.sales.models import Booking, BookingStatusEnum
from minirail.utils.date_utils import utc_now
from tests.sales.conftest import create_booking_via_api


def _booking(session: Session, booking_key: str) -> Booking:
    return session.scalars(select(Booking).where(Booking.booking_key == booking_key)).one()


def _leg_counts(session: Session, od: OD) -> list[int]:
    legs = session.scalars(select(Leg).where(Leg.service_id == od.service_id).order_by(Leg.rank)).all()
    return [leg.seats_booked for leg in legs]


def test_expire_overdue_pending_booking(
    client: TestClient, auth_headers: dict[str, str], session: Session, paris_marseille_od: OD
) -> None:
    body = create_booking_via_api(client, auth_headers, session, paris_marseille_od.id, passenger_count=2)
    booking = _booking(session, body["bookingKey"])
    booking.expires_at = utc_now() - timedelta(seconds=1)
    session.flush()

    result = ExpireBookingJob(session=session, booking_id=booking.id).call()

    assert result.output is True
    assert booking.status is BookingStatusEnum.EXPIRED
    assert _leg_counts(session, paris_marseille_od) == [0, 0]


def test_expiry_is_a_noop_on_confirmed_booking(
    client: TestClient, auth_headers: dict[str, str], session: Session, paris_marseille_od: OD
) -> None:
    """The double-release guard.

    The expiry message fires even for bookings that were confirmed in the
    meantime (it was scheduled at creation). If the status guard in
    ExpireBookingJob were missing, this would strip seats from a *paid*
    booking — or release seats twice for a cancelled one.
    """
    body = create_booking_via_api(client, auth_headers, session, paris_marseille_od.id, passenger_count=2)
    confirm = client.post(
        f"/api/bookings/{body['bookingKey']}/confirm", headers=auth_headers, json={"paymentToken": "tok_ok"}
    )
    assert confirm.status_code == 200
    booking = _booking(session, body["bookingKey"])

    result = ExpireBookingJob(session=session, booking_id=booking.id).call()

    assert result.output is False
    assert booking.status is BookingStatusEnum.CONFIRMED
    assert _leg_counts(session, paris_marseille_od) == [2, 2], "confirmed seats must stay booked"


def test_expiry_is_a_noop_before_the_deadline(
    client: TestClient, auth_headers: dict[str, str], session: Session, paris_marseille_od: OD
) -> None:
    body = create_booking_via_api(client, auth_headers, session, paris_marseille_od.id)
    booking = _booking(session, body["bookingKey"])

    result = ExpireBookingJob(session=session, booking_id=booking.id).call()

    assert result.output is False
    assert booking.status is BookingStatusEnum.PENDING


def test_find_stale_booking_ids_only_returns_overdue_pending(
    client: TestClient, auth_headers: dict[str, str], session: Session, paris_marseille_od: OD
) -> None:
    fresh = create_booking_via_api(client, auth_headers, session, paris_marseille_od.id, passenger_count=1)
    overdue = create_booking_via_api(client, auth_headers, session, paris_marseille_od.id, passenger_count=1)
    confirmed = create_booking_via_api(client, auth_headers, session, paris_marseille_od.id, passenger_count=1)

    _booking(session, overdue["bookingKey"]).expires_at = utc_now() - timedelta(minutes=1)
    confirmed_booking = _booking(session, confirmed["bookingKey"])
    assert (
        client.post(
            f"/api/bookings/{confirmed['bookingKey']}/confirm", headers=auth_headers, json={"paymentToken": "tok_ok"}
        ).status_code
        == 200
    )
    session.flush()

    stale_ids = find_stale_booking_ids(session)
    overdue_id = _booking(session, overdue["bookingKey"]).id

    assert overdue_id in stale_ids
    assert _booking(session, fresh["bookingKey"]).id not in stale_ids
    assert confirmed_booking.id not in stale_ids
