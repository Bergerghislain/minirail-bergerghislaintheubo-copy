from datetime import timedelta
from typing import cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from minirail.inventory.models import OD
from minirail.sales.jobs.expire_booking import ExpireBookingJob
from minirail.sales.models import (
    Booking,
    DiscountCode,
    DiscountRedemption,
    DiscountRedemptionStatusEnum,
    SalesChannel,
)
from minirail.sales.service.discount_code import release_discount_use_for_booking
from minirail.utils.date_utils import utc_now
from tests.factories import DiscountCodeFactory, SalesChannelFactory
from tests.sales.conftest import create_booking_via_api


def _redemption(session: Session, booking_id: int) -> DiscountRedemption:
    return session.scalars(select(DiscountRedemption).where(DiscountRedemption.booking_id == booking_id)).one()


def _discount(session: Session, code: str = "SAVE10") -> DiscountCode:
    return session.scalars(select(DiscountCode).where(DiscountCode.code == code)).one()


def test_create_journals_reserved_redemption(client: TestClient, session: Session, paris_marseille_od: OD) -> None:
    channel = SalesChannelFactory()
    DiscountCodeFactory(sales_channel=channel, code="SAVE10", percent_off=10, max_uses=100)
    headers = {"X-API-Key": channel.api_key}

    body = create_booking_via_api(
        client, headers, session, paris_marseille_od.id, passenger_count=1, discount_code="SAVE10"
    )
    booking = session.scalars(select(Booking).where(Booking.booking_key == body["bookingKey"])).one()

    redemption = _redemption(session, booking.id)
    assert redemption.status is DiscountRedemptionStatusEnum.RESERVED
    assert redemption.discount_code_id == booking.discount_code_id
    assert _discount(session).use_count == 1


def test_cancel_pending_releases_redemption_atomically(
    client: TestClient, session: Session, paris_marseille_od: OD
) -> None:
    channel = SalesChannelFactory()
    DiscountCodeFactory(sales_channel=channel, code="SAVE10", percent_off=10)
    headers = {"X-API-Key": channel.api_key}
    body = create_booking_via_api(
        client, headers, session, paris_marseille_od.id, passenger_count=1, discount_code="SAVE10"
    )
    booking = session.scalars(select(Booking).where(Booking.booking_key == body["bookingKey"])).one()

    assert client.post(f"/api/bookings/{body['bookingKey']}/cancel", headers=headers).status_code == 200
    session.expire_all()

    assert _redemption(session, booking.id).status is DiscountRedemptionStatusEnum.RELEASED
    assert _discount(session).use_count == 0

    # Second release is a no-op (atomic UPDATE matched 0 rows).
    assert release_discount_use_for_booking(session, booking) is False
    assert _discount(session).use_count == 0


def test_expire_pending_releases_redemption(client: TestClient, session: Session, paris_marseille_od: OD) -> None:
    channel = SalesChannelFactory()
    DiscountCodeFactory(sales_channel=channel, code="SAVE10", percent_off=10)
    headers = {"X-API-Key": channel.api_key}
    body = create_booking_via_api(
        client, headers, session, paris_marseille_od.id, passenger_count=1, discount_code="SAVE10"
    )
    booking = session.scalars(select(Booking).where(Booking.booking_key == body["bookingKey"])).one()
    booking.expires_at = utc_now() - timedelta(seconds=1)
    session.flush()

    assert ExpireBookingJob(session=session, booking_id=booking.id).call().output is True

    assert _redemption(session, booking.id).status is DiscountRedemptionStatusEnum.RELEASED
    assert _discount(session).use_count == 0


def test_confirm_consumes_redemption_and_keeps_use_on_cancel(
    client: TestClient, session: Session, paris_marseille_od: OD
) -> None:
    channel = SalesChannelFactory()
    DiscountCodeFactory(sales_channel=channel, code="SAVE10", percent_off=10)
    headers = {"X-API-Key": channel.api_key}
    body = create_booking_via_api(
        client, headers, session, paris_marseille_od.id, passenger_count=1, discount_code="SAVE10"
    )
    booking = session.scalars(select(Booking).where(Booking.booking_key == body["bookingKey"])).one()

    assert (
        client.post(
            f"/api/bookings/{body['bookingKey']}/confirm", headers=headers, json={"paymentToken": "tok_ok"}
        ).status_code
        == 200
    )
    session.expire_all()
    assert _redemption(session, booking.id).status is DiscountRedemptionStatusEnum.CONSUMED
    assert _discount(session).use_count == 1

    assert client.post(f"/api/bookings/{body['bookingKey']}/cancel", headers=headers).status_code == 200
    session.expire_all()
    assert _redemption(session, booking.id).status is DiscountRedemptionStatusEnum.CONSUMED
    assert _discount(session).use_count == 1


def _flush_invalid_discount(
    session: Session, channel: SalesChannel, *, code: str, percent_off: int, max_uses: int, use_count: int
) -> None:
    with session.begin_nested():
        session.add(
            DiscountCode(
                sales_channel=channel,
                code=code,
                percent_off=percent_off,
                max_uses=max_uses,
                use_count=use_count,
            )
        )
        session.flush()


def test_discount_code_checks_reject_invalid_rows(session: Session) -> None:
    channel = cast(SalesChannel, SalesChannelFactory())

    with pytest.raises(IntegrityError):
        _flush_invalid_discount(session, channel, code="bad", percent_off=10, max_uses=10, use_count=0)
    with pytest.raises(IntegrityError):
        _flush_invalid_discount(session, channel, code="BAD", percent_off=0, max_uses=10, use_count=0)
    with pytest.raises(IntegrityError):
        _flush_invalid_discount(session, channel, code="BAD", percent_off=10, max_uses=0, use_count=0)
    with pytest.raises(IntegrityError):
        _flush_invalid_discount(session, channel, code="BAD", percent_off=10, max_uses=5, use_count=6)
