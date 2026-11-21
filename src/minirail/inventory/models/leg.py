from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from minirail.orm import Base, UTCDateTime

if TYPE_CHECKING:
    from minirail.inventory.models.service import Service
    from minirail.inventory.models.station import Station


class Leg(Base):
    """A station-to-station segment of a service; the unit of seat inventory.

    Seat counting happens here: an OD spanning several legs consumes one seat
    on each of them. `seats_booked` is maintained by
    minirail.inventory.service.seat_inventory, the only module allowed to
    write it.
    """

    __tablename__ = "leg"
    __table_args__ = (UniqueConstraint("service_id", "rank"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("service.id"))
    # Position of the leg within the service, starting at 1.
    rank: Mapped[int]
    origin_station_id: Mapped[int] = mapped_column(ForeignKey("station.id"))
    destination_station_id: Mapped[int] = mapped_column(ForeignKey("station.id"))
    departure_at: Mapped[datetime] = mapped_column(UTCDateTime())
    arrival_at: Mapped[datetime] = mapped_column(UTCDateTime())
    seat_capacity: Mapped[int]
    seats_booked: Mapped[int] = mapped_column(default=0)

    service: Mapped[Service] = relationship(back_populates="legs")
    origin_station: Mapped[Station] = relationship(foreign_keys=[origin_station_id])
    destination_station: Mapped[Station] = relationship(foreign_keys=[destination_station_id])
