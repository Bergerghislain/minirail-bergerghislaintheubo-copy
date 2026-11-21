from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from minirail.orm import Base

if TYPE_CHECKING:
    from minirail.inventory.models.service import Service
    from minirail.inventory.models.station import Station


class OD(Base):
    """A sellable origin-destination on a service, at a price.

    An OD spans the legs whose rank lies in [first_leg_rank, last_leg_rank]:
    on a Paris→Lyon→Marseille service, the Paris→Marseille OD spans both legs
    and its availability is the minimum of their remaining seats.
    """

    __tablename__ = "od"
    __table_args__ = (UniqueConstraint("service_id", "origin_station_id", "destination_station_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("service.id"))
    origin_station_id: Mapped[int] = mapped_column(ForeignKey("station.id"))
    destination_station_id: Mapped[int] = mapped_column(ForeignKey("station.id"))
    first_leg_rank: Mapped[int]
    last_leg_rank: Mapped[int]
    # Money is always Decimal in this codebase — never float.
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")

    service: Mapped[Service] = relationship(back_populates="ods")
    origin_station: Mapped[Station] = relationship(foreign_keys=[origin_station_id])
    destination_station: Mapped[Station] = relationship(foreign_keys=[destination_station_id])
