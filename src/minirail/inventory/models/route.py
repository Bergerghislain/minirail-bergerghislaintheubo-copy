from typing import TYPE_CHECKING

from sqlalchemy.orm import Mapped, mapped_column, relationship

from minirail.orm import Base

if TYPE_CHECKING:
    from minirail.inventory.models.service import Service


class Route(Base):
    """A commercial line, e.g. Paris → Marseille. Services are its dated runs."""

    __tablename__ = "route"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(unique=True)  # e.g. "PAR-MRS"
    name: Mapped[str]

    services: Mapped[list[Service]] = relationship(back_populates="route")
