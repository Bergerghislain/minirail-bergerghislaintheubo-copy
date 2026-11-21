"""Prove the transaction-as-you-go harness: both tests insert the same unique
station code and commit; if isolation leaked, the second one would violate the
unique constraint."""

from sqlalchemy.orm import Session

from minirail.inventory.models import Station


def _insert_and_commit(session: Session) -> None:
    session.add(Station(code="FRISO", name="Isolation City", timezone="Europe/Paris"))
    session.commit()
    assert session.query(Station).filter_by(code="FRISO").count() == 1


def test_unique_insert_first(session: Session) -> None:
    _insert_and_commit(session)


def test_unique_insert_second(session: Session) -> None:
    _insert_and_commit(session)
