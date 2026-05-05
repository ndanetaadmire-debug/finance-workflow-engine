"""Money as Decimal with explicit currency. Floats never touch an amount."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str = "ZAR"

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise TypeError("Money.amount must be Decimal")
        object.__setattr__(self, "amount", self.amount.quantize(CENT, rounding=ROUND_HALF_UP))
        if len(self.currency) != 3:
            raise ValueError("currency must be ISO-4217")

    @classmethod
    def of(cls, value: str | int | Decimal, currency: str = "ZAR") -> Money:
        return cls(Decimal(str(value)), currency)

    def _check(self, other: Money) -> None:
        if other.currency != self.currency:
            raise ValueError(f"currency mismatch: {self.currency} vs {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: Decimal | int) -> Money:
        return Money(self.amount * Decimal(factor), self.currency)

    def abs_diff(self, other: Money) -> Decimal:
        self._check(other)
        return abs(self.amount - other.amount)

    def within(self, other: Money, *, pct: Decimal = Decimal("0"), absolute: Decimal = CENT) -> bool:
        """True if the two amounts agree within max(absolute, pct of the larger)."""
        tolerance = max(absolute, max(abs(self.amount), abs(other.amount)) * pct)
        return self.abs_diff(other) <= tolerance

    def __str__(self) -> str:
        return f"{self.currency} {self.amount:,.2f}"


def zero(currency: str = "ZAR") -> Money:
    return Money(Decimal("0"), currency)
