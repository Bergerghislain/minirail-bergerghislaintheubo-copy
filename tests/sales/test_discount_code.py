from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from minirail.sales.service.discount_code import normalize_discount_code, validate_discount_code
from minirail.utils.date_utils import utc_now
from minirail.utils.exc import (
    DiscountCodeExhaustedException,
    DiscountNotApplicableException,
    InvalidDiscountCodeException,
)
from tests.factories import DiscountCodeFactory, SalesChannelFactory

_MIN_PRICE = Decimal("20.00")
_TOTAL_OK = Decimal("80.00")


def test_normalize_discount_code_trims_and_uppercases() -> None:
    assert normalize_discount_code("  save10  ") == "SAVE10"


def test_validate_discount_code_happy_path(session: Session) -> None:
    channel = SalesChannelFactory()
    discount = DiscountCodeFactory(sales_channel=channel, code="SAVE10")

    result = validate_discount_code(
        session,
        sales_channel_id=channel.id,
        code="  save10  ",
        booking_total=_TOTAL_OK,
        min_price=_MIN_PRICE,
    )

    assert result.id == discount.id
    assert result.use_count == 0  # validation does not reserve a use


def test_unknown_code_is_invalid(session: Session) -> None:
    channel = SalesChannelFactory()

    with pytest.raises(InvalidDiscountCodeException) as exc_info:
        validate_discount_code(
            session,
            sales_channel_id=channel.id,
            code="NOPE",
            booking_total=_TOTAL_OK,
            min_price=_MIN_PRICE,
        )

    assert exc_info.value.error_code.value == "invalid_discount_code"


def test_other_channel_code_is_invalid_same_error(session: Session) -> None:
    owner = SalesChannelFactory()
    other = SalesChannelFactory()
    DiscountCodeFactory(sales_channel=owner, code="SAVE10")

    with pytest.raises(InvalidDiscountCodeException) as exc_info:
        validate_discount_code(
            session,
            sales_channel_id=other.id,
            code="SAVE10",
            booking_total=_TOTAL_OK,
            min_price=_MIN_PRICE,
        )

    assert exc_info.value.error_code.value == "invalid_discount_code"


def test_inactive_code_is_invalid(session: Session) -> None:
    channel = SalesChannelFactory()
    DiscountCodeFactory(sales_channel=channel, code="SAVE10", is_active=False)

    with pytest.raises(InvalidDiscountCodeException):
        validate_discount_code(
            session,
            sales_channel_id=channel.id,
            code="SAVE10",
            booking_total=_TOTAL_OK,
            min_price=_MIN_PRICE,
        )


def test_expired_code_is_invalid(session: Session) -> None:
    channel = SalesChannelFactory()
    DiscountCodeFactory(
        sales_channel=channel,
        code="SAVE10",
        valid_until=utc_now() - timedelta(minutes=1),
    )

    with pytest.raises(InvalidDiscountCodeException):
        validate_discount_code(
            session,
            sales_channel_id=channel.id,
            code="SAVE10",
            booking_total=_TOTAL_OK,
            min_price=_MIN_PRICE,
        )


def test_exhausted_code_raises_exhausted(session: Session) -> None:
    channel = SalesChannelFactory()
    DiscountCodeFactory(sales_channel=channel, code="SAVE10", max_uses=5, use_count=5)

    with pytest.raises(DiscountCodeExhaustedException) as exc_info:
        validate_discount_code(
            session,
            sales_channel_id=channel.id,
            code="SAVE10",
            booking_total=_TOTAL_OK,
            min_price=_MIN_PRICE,
        )

    assert exc_info.value.error_code.value == "discount_code_exhausted"


def test_below_min_price_raises_not_applicable(session: Session) -> None:
    channel = SalesChannelFactory()
    DiscountCodeFactory(sales_channel=channel, code="SAVE10")

    with pytest.raises(DiscountNotApplicableException) as exc_info:
        validate_discount_code(
            session,
            sales_channel_id=channel.id,
            code="SAVE10",
            booking_total=Decimal("19.99"),
            min_price=_MIN_PRICE,
        )

    assert exc_info.value.error_code.value == "discount_not_applicable"
