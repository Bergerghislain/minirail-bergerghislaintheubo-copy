"""Discount-code primitives: normalize, lock, validate, reserve, release.

Everything here flushes and never commits — the caller owns the transaction.
"""

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select

from minirail.orm import MinirailSession
from minirail.sales.models import Booking, DiscountCode
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


def reserve_discount_use(session: MinirailSession, discount: DiscountCode) -> None:
    """Consume one use on an already-validated, locked discount row."""
    discount.use_count += 1
    session.flush()


def release_discount_use_for_booking(session: MinirailSession, booking: Booking) -> None:
    """Give back one use when a PENDING booking with a promo is cancelled/expired.

    No-op when the booking has no discount. Locks the code row so concurrent
    reservations cannot race the decrement.
    """
    if booking.discount_code_id is None:
        return
    statement = select(DiscountCode).where(DiscountCode.id == booking.discount_code_id).with_for_update()
    discount = session.scalars(statement).one_or_none()
    if discount is None:
        return
    if discount.use_count > 0:
        discount.use_count -= 1
    session.flush()
