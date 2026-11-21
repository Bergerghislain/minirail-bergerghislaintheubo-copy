from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from minirail.orm import Base

if TYPE_CHECKING:
    from minirail.inventory.models.od import OD
    from minirail.sales.models.booking import Booking
    from minirail.sales.models.passenger import Passenger


class TicketStatusEnum(StrEnum):
    HELD = "HELD"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class Ticket(Base):
    """One passenger's right to travel on one OD. Mirrors its booking's lifecycle."""

    __tablename__ = "ticket"
    __table_args__ = (UniqueConstraint("passenger_id", "od_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("booking.id"))
    passenger_id: Mapped[int] = mapped_column(ForeignKey("passenger.id"))
    od_id: Mapped[int] = mapped_column(ForeignKey("od.id"))
    status: Mapped[TicketStatusEnum] = mapped_column(
        Enum(TicketStatusEnum, native_enum=False, length=20),
        default=TicketStatusEnum.HELD,
    )
    # The OD's price at the moment of sale: OD prices can change later,
    # sold tickets must not.
    price_at_sale: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    booking: Mapped[Booking] = relationship(back_populates="tickets")
    passenger: Mapped[Passenger] = relationship(back_populates="tickets")
    od: Mapped[OD] = relationship()
