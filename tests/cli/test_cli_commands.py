"""Smoke tests for CLI entry points (Click CliRunner).

Guards the model-registry load and the operator-facing validation that used
to surface raw IntegrityError / InvalidOperation traces.
"""

from datetime import UTC, datetime
from decimal import Decimal

from click.testing import CliRunner
from sqlalchemy import select
from sqlalchemy.orm import Session

from minirail.cli import cli
from minirail.sales.models import DiscountCode, SalesChannel
from tests.factories import SalesChannelFactory


def test_create_sales_channel_loads_model_registry_and_prints_key(session: Session) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["create-sales-channel", "cli-smoke-channel"])
    assert result.exit_code == 0, result.output
    assert "API key:" in result.output
    channel = session.scalars(select(SalesChannel).where(SalesChannel.name == "cli-smoke-channel")).one()
    assert channel.api_key


def test_create_discount_code_happy_path(session: Session) -> None:
    SalesChannelFactory(name="promo-channel")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["create-discount-code", "promo-channel", "save10", "--percent-off", "10", "--max-uses", "5"],
    )
    assert result.exit_code == 0, result.output
    code = session.scalars(select(DiscountCode).where(DiscountCode.code == "SAVE10")).one()
    assert code.percent_off == Decimal("10.00")
    assert code.max_uses == 5


def test_create_discount_code_rejects_duplicate(session: Session) -> None:
    channel = SalesChannelFactory(name="dup-channel")
    session.add(
        DiscountCode(
            sales_channel_id=channel.id,
            code="DUP",
            percent_off=Decimal("10.00"),
            max_uses=1,
        )
    )
    session.flush()

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["create-discount-code", "dup-channel", "dup", "--percent-off", "10", "--max-uses", "1"],
    )
    assert result.exit_code != 0
    assert "already exists" in result.output
    assert "IntegrityError" not in result.output


def test_create_discount_code_rejects_non_numeric_percent(session: Session) -> None:
    SalesChannelFactory(name="bad-pct")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["create-discount-code", "bad-pct", "X", "--percent-off", "abc", "--max-uses", "1"],
    )
    assert result.exit_code != 0
    assert "must be a number" in result.output
    assert "InvalidOperation" not in result.output
    assert "Traceback" not in result.output


def test_create_discount_code_rejects_too_many_decimals(session: Session) -> None:
    SalesChannelFactory(name="decimals")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["create-discount-code", "decimals", "X", "--percent-off", "12.345", "--max-uses", "1"],
    )
    assert result.exit_code != 0
    assert "2 decimal" in result.output


def test_create_discount_code_date_only_valid_until_is_end_of_day(session: Session) -> None:
    SalesChannelFactory(name="until-channel")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "create-discount-code",
            "until-channel",
            "DAY",
            "--percent-off",
            "10",
            "--max-uses",
            "1",
            "--valid-until",
            "2026-12-31",
        ],
    )
    assert result.exit_code == 0, result.output
    code = session.scalars(select(DiscountCode).where(DiscountCode.code == "DAY")).one()
    assert code.valid_until == datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
