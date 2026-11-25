"""Discount-code primitives: normalize, lock, validate, reserve, release, consume.

Everything here flushes and never commits — the caller owns the transaction.
``use_count`` remains the fast quota counter; ``discount_redemption`` is the journal.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult

from minirail.orm import MinirailSession
from minirail.sales.models import Booking, DiscountCode
from minirail.sales.models.discount_redemption import DiscountRedemption, DiscountRedemptionStatusEnum
from minirail.utils.date_utils import utc_now
from minirail.utils.exc import (
    DiscountCodeExhaustedException,
    DiscountNotApplicableException,
    InvalidDiscountCodeException,
)


def normalize_discount_code(code: str) -> str:
    """Trim and uppercase so lookups match how codes are stored."""
    return code.strip().upper()


def compute_discount_amount(booking_total: Decimal, percent_off: int) -> Decimal:
    """Percent-off of ``booking_total``, rounded to cents with ROUND_HALF_UP."""
    raw = booking_total * Decimal(percent_off) / Decimal(100)
    return raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def validate_discount_code(
    session: MinirailSession,
    *,
    sales_channel_id: int,
    code: str,
    booking_total: Decimal,
    min_price: Decimal,
) -> DiscountCode:
    """Lock and validate a percent-off code for the authenticated channel.

    Raises:
        InvalidDiscountCodeException: unknown, inactive, expired, or owned by
            another channel (same public error — see exception docstring).
        DiscountCodeExhaustedException: ``use_count >= max_uses``.
        DiscountNotApplicableException: ``booking_total < min_price``.

    The row is locked with ``SELECT ... FOR UPDATE`` so a concurrent booking
    cannot both pass the quota check before either increments ``use_count``.
    """
    normalized = normalize_discount_code(code)
    if not normalized:
        raise InvalidDiscountCodeException("Invalid discount code")

    statement = (
        select(DiscountCode)
        .where(
            DiscountCode.sales_channel_id == sales_channel_id,
            DiscountCode.code == normalized,
        )
        .with_for_update()
    )
    discount = session.scalars(statement).one_or_none()

    # Missing row covers both "never existed" and "belongs to another channel":
    # the query is scoped to sales_channel_id on purpose.
    if discount is None or not discount.is_active:
        raise InvalidDiscountCodeException("Invalid discount code")

    if discount.valid_until is not None and utc_now() >= discount.valid_until:
        raise InvalidDiscountCodeException("Invalid discount code")

    if discount.use_count >= discount.max_uses:
        raise DiscountCodeExhaustedException(f"Discount code {normalized} has reached its maximum number of uses")

    if booking_total < min_price:
        raise DiscountNotApplicableException(
            f"Booking total {booking_total} is below the minimum price {min_price} for a discount"
        )

    return discount


def reserve_discount_use(session: MinirailSession, discount: DiscountCode, booking: Booking) -> DiscountRedemption:
    """Increment ``use_count`` and journal a RESERVED redemption for ``booking``."""
    discount.use_count += 1
    now = utc_now()
    redemption = DiscountRedemption(
        discount_code_id=discount.id,
        booking_id=booking.id,
        status=DiscountRedemptionStatusEnum.RESERVED,
        created_at=now,
        updated_at=now,
    )
    session.add(redemption)
    session.flush()
    return redemption


def release_discount_use_for_booking(session: MinirailSession, booking: Booking) -> bool:
    """Atomically RESERVED → RELEASED and decrement ``use_count`` if the transition won.

    Returns True when a use was actually released. Safe under concurrent
    cancel/expire: a second caller sees rowcount 0 and leaves the counter alone.
    """
    if booking.discount_code_id is None:
        return False

    now = utc_now()
    result = cast(
        CursorResult[Any],
        session.execute(
            update(DiscountRedemption)
            .where(
                DiscountRedemption.booking_id == booking.id,
                DiscountRedemption.status == DiscountRedemptionStatusEnum.RESERVED,
            )
            .values(status=DiscountRedemptionStatusEnum.RELEASED, updated_at=now)
        ),
    )
    if result.rowcount != 1:
        session.flush()
        return False

    session.execute(
        update(DiscountCode)
        .where(DiscountCode.id == booking.discount_code_id, DiscountCode.use_count > 0)
        .values(use_count=DiscountCode.use_count - 1)
    )
    session.flush()
    return True


def consume_discount_use_for_booking(session: MinirailSession, booking: Booking) -> bool:
    """Atomically RESERVED → CONSUMED on confirm. ``use_count`` stays consumed.

    Returns True when the transition applied.
    """
    if booking.discount_code_id is None:
        return False

    now = utc_now()
    result = cast(
        CursorResult[Any],
        session.execute(
            update(DiscountRedemption)
            .where(
                DiscountRedemption.booking_id == booking.id,
                DiscountRedemption.status == DiscountRedemptionStatusEnum.RESERVED,
            )
            .values(status=DiscountRedemptionStatusEnum.CONSUMED, updated_at=now)
        ),
    )
    session.flush()
    return result.rowcount == 1
