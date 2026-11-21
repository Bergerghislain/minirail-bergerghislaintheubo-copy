from sqlalchemy.orm import Mapped, mapped_column

from minirail.orm import Base


class SalesChannel(Base):
    """A distributor allowed to sell through the API, identified by its API key."""

    __tablename__ = "sales_channel"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    api_key: Mapped[str] = mapped_column(unique=True)
    is_active: Mapped[bool] = mapped_column(default=True)
