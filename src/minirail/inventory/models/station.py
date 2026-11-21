from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from minirail.orm import Base


class Station(Base):
    __tablename__ = "station"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Short station identifier, e.g. "FRPAR" (Paris), "FRMRS" (Marseille).
    code: Mapped[str] = mapped_column(String(5), unique=True)
    name: Mapped[str]
    # IANA timezone name, e.g. "Europe/Paris". Times are stored in UTC and
    # rendered in the station's local timezone by clients.
    timezone: Mapped[str]
