from datetime import date
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from minirail.orm import Base

if TYPE_CHECKING:
    from minirail.inventory.models.leg import Leg
    from minirail.inventory.models.od import OD
    from minirail.inventory.models.route import Route


class ServiceStatusEnum(StrEnum):
    SCHEDULED = "SCHEDULED"
    CANCELLED = "CANCELLED"


class Service(Base):
    """One dated run of a route: train 6103 on route PAR-MRS on 2026-08-15."""

    __tablename__ = "service"
    __table_args__ = (UniqueConstraint("route_id", "service_date", "train_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("route.id"))
    service_date: Mapped[date]
    train_number: Mapped[str]
    status: Mapped[ServiceStatusEnum] = mapped_column(
        # native_enum=False stores a VARCHAR with a CHECK constraint instead of
        # a PostgreSQL ENUM type: adding a value later is a one-line migration.
        Enum(ServiceStatusEnum, native_enum=False, length=20),
        default=ServiceStatusEnum.SCHEDULED,
    )

    route: Mapped[Route] = relationship(back_populates="services")
    legs: Mapped[list[Leg]] = relationship(back_populates="service", order_by="Leg.rank")
    ods: Mapped[list[OD]] = relationship(back_populates="service")
