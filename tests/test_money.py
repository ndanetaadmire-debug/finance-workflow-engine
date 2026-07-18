from decimal import Decimal

import pytest

from fwe.domain.money import Money


def test_rounds_half_up_to_cents() -> None:
    assert Money(Decimal("10.005")).amount == Decimal("10.01")


def test_rejects_floats_and_currency_mixing() -> None:
    with pytest.raises(TypeError):
        Money(10.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="currency mismatch"):
        Money.of("1") + Money.of("1", "USD")


def test_tolerance() -> None:
    assert Money.of("100.00").within(Money.of("101.50"), pct=Decimal("0.02"))
    assert not Money.of("100.00").within(Money.of("103.00"), pct=Decimal("0.02"))
    assert Money.of("100.00").within(Money.of("100.01"))
