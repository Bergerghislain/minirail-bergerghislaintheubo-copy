from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from minirail.orm import Base

if TYPE_CHECKING:
    from minirail.sales.models.booking import Booking
    from minirail.sales.models.ticket import Ticket


class Passenger(Base):
    __tablename__ = "passenger"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("booking.id"))
    first_name: Mapped[str]
    last_name: Mapped[str]

    booking: Mapped[Booking] = relationship(back_populates="passengers")
    tickets: Mapped[list[Ticket]] = relationship(back_populates="passenger")
