from datetime import datetime
from decimal import Decimal

from pydantic import Field, field_validator

from minirail.sales.models import BookingStatusEnum, DiscountCode, TicketStatusEnum
from minirail.utils.schema import Schema


class PassengerInputSchema(Schema):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)


class BookingCreateSchema(Schema):
    od_id: int
    passengers: list[PassengerInputSchema] = Field(min_length=1, max_length=9)
    # Promotion code owned by the calling sales channel; any casing accepted.
    discount_code: str | None = Field(default=None, min_length=1, max_length=32)


class BookingConfirmSchema(Schema):
    payment_token: str = Field(min_length=1)


class BookingPassengerSchema(Schema):
    id: int
    first_name: str
    last_name: str


class BookingTicketSchema(Schema):
    passenger_id: int
    od_id: int
    status: TicketStatusEnum
    price_at_sale: Decimal


class BookingOutputSchema(Schema):
    booking_key: str
    pnr: str
    status: BookingStatusEnum
    total_amount: Decimal
    currency: str
    discount_amount: Decimal
    discount_code: str | None = None
    expires_at: datetime | None
    confirmed_at: datetime | None
    created_at: datetime
    passengers: list[BookingPassengerSchema]
    tickets: list[BookingTicketSchema]

    @field_validator("discount_code", mode="before")
    @classmethod
    def _code_as_string(cls, value: DiscountCode | str | None) -> str | None:
        """The ORM attribute is the DiscountCode row; the API exposes its code."""
        return value.code if isinstance(value, DiscountCode) else value
