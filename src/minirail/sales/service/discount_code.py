"""Discount-code primitives: normalize, lock, and validate.

Everything here flushes and never commits — the caller owns the transaction.
Does not increment ``use_count``; reservation belongs to the booking job.
"""

from decimal import Decimal

from sqlalchemy import select

from minirail.orm import MinirailSession
from minirail.sales.models import DiscountCode
from minirail.utils.date_utils import utc_now
from minirail.utils.exc import (
    DiscountCodeExhaustedException,
    DiscountNotApplicableException,
    InvalidDiscountCodeException,
)


def normalize_discount_code(code: str) -> str:
    """Trim and uppercase so lookups match how codes are stored."""
    return code.strip().upper()


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
