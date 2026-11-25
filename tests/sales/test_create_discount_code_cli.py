from datetime import UTC, datetime

from click.testing import CliRunner
from sqlalchemy import select
from sqlalchemy.orm import Session

from minirail.cli import cli
from minirail.sales.models import DiscountCode
from tests.factories import DiscountCodeFactory, SalesChannelFactory


def test_create_discount_code_happy_path(session: Session) -> None:
    SalesChannelFactory(name="partner")
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["create-discount-code", "partner", "  save10  ", "--percent-off", "10", "--max-uses", "100"],
    )

    assert result.exit_code == 0, result.output
    assert "SAVE10" in result.output
    discount = session.scalars(select(DiscountCode).where(DiscountCode.code == "SAVE10")).one()
    assert discount.percent_off == 10
    assert discount.max_uses == 100
    assert discount.valid_until is None
    assert discount.use_count == 0


def test_create_discount_code_with_valid_until(session: Session) -> None:
    SalesChannelFactory(name="partner")
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "create-discount-code",
            "partner",
            "SUMMER",
            "--percent-off",
            "15",
            "--max-uses",
            "50",
            "--valid-until",
            "2030-12-31T23:59:59",
        ],
    )

    assert result.exit_code == 0, result.output
    discount = session.scalars(select(DiscountCode).where(DiscountCode.code == "SUMMER")).one()
    assert discount.valid_until == datetime(2030, 12, 31, 23, 59, 59, tzinfo=UTC)


def test_create_discount_code_unknown_channel(session: Session) -> None:
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["create-discount-code", "missing", "SAVE10", "--percent-off", "10", "--max-uses", "100"],
    )

    assert result.exit_code != 0
    assert "Unknown sales channel" in result.output


def test_create_discount_code_invalid_percent(session: Session) -> None:
    SalesChannelFactory(name="partner")
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["create-discount-code", "partner", "SAVE10", "--percent-off", "0", "--max-uses", "100"],
    )

    assert result.exit_code != 0
    assert "--percent-off" in result.output


def test_create_discount_code_duplicate(session: Session) -> None:
    channel = SalesChannelFactory(name="partner")
    DiscountCodeFactory(sales_channel=channel, code="SAVE10")
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["create-discount-code", "partner", "save10", "--percent-off", "10", "--max-uses", "100"],
    )

    assert result.exit_code != 0
    assert "already exists" in result.output
