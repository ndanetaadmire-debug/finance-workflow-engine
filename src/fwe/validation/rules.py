"""Validation rules. Each rule is a pure function: (invoice, context) -> findings.

Rules are small, independently testable and ordered. BLOCK findings stop
straight-through processing and route the invoice to a human.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from fwe.domain.models import ExtractedInvoice, Finding, Severity, Vendor
from fwe.domain.money import Money

VAT_RATE = Decimal("0.15")


@dataclass(frozen=True, slots=True)
class ValidationContext:
    vendor: Vendor | None
    today: date
    prior_invoices: Sequence[tuple[str, str, Money]]  # (vendor_id, invoice_number, total)
    min_confidence: float = 0.8


Rule = Callable[[ExtractedInvoice, ValidationContext], Iterable[Finding]]


def known_vendor(inv: ExtractedInvoice, ctx: ValidationContext) -> Iterable[Finding]:
    if ctx.vendor is None:
        yield Finding("VENDOR_UNKNOWN", Severity.BLOCK, f"No vendor master record for '{inv.vendor_name.value}'")


def bank_details_match(inv: ExtractedInvoice, ctx: ValidationContext) -> Iterable[Finding]:
    """The #1 AP fraud vector: an invoice that 'updates' the supplier's bank account."""
    if ctx.vendor and inv.bank_account.value and inv.bank_account.value != ctx.vendor.bank_account:
        yield Finding(
            "BANK_DETAILS_CHANGED",
            Severity.BLOCK,
            "Bank account on invoice differs from vendor master. Verify by phone before paying.",
        )


def vat_number_matches(inv: ExtractedInvoice, ctx: ValidationContext) -> Iterable[Finding]:
    if ctx.vendor and ctx.vendor.vat_number and inv.vendor_vat_number.value not in (None, ctx.vendor.vat_number):
        yield Finding("VAT_NUMBER_MISMATCH", Severity.BLOCK, "VAT registration number differs from vendor master")


def arithmetic(inv: ExtractedInvoice, _ctx: ValidationContext) -> Iterable[Finding]:
    sub, vat, total = inv.subtotal.value, inv.vat.value, inv.total.value
    if not (sub + vat).within(total):
        yield Finding("TOTAL_MISMATCH", Severity.BLOCK, f"Subtotal {sub} + VAT {vat} ≠ total {total}")
    if not (sub * VAT_RATE).within(vat, absolute=Decimal("0.05")):
        yield Finding("VAT_RATE", Severity.WARN, f"VAT {vat} is not 15% of {sub}")
    if inv.lines:
        lines_total = sum((li.total for li in inv.lines), Money(Decimal("0"), sub.currency))
        if not lines_total.within(sub):
            yield Finding("LINES_MISMATCH", Severity.BLOCK, f"Line items sum to {lines_total}, subtotal is {sub}")


def duplicate(inv: ExtractedInvoice, ctx: ValidationContext) -> Iterable[Finding]:
    if ctx.vendor is None:
        return
    norm = inv.invoice_number.value.upper().replace("-", "").lstrip("0")
    for vendor_id, number, total in ctx.prior_invoices:
        if vendor_id != ctx.vendor.id:
            continue
        if number.upper().replace("-", "").lstrip("0") == norm:
            yield Finding("DUPLICATE", Severity.BLOCK, f"Invoice {number} from this vendor was already captured")
            return
        if total == inv.total.value:
            yield Finding("POSSIBLE_DUPLICATE", Severity.WARN, f"Same amount as prior invoice {number}")


def dates(inv: ExtractedInvoice, ctx: ValidationContext) -> Iterable[Finding]:
    d = inv.invoice_date.value
    if d > ctx.today + timedelta(days=1):
        yield Finding("FUTURE_DATED", Severity.BLOCK, f"Invoice dated in the future ({d})")
    elif d < ctx.today - timedelta(days=365):
        yield Finding("STALE", Severity.WARN, f"Invoice older than 12 months ({d})")
    due = inv.due_date.value
    if due and due < d:
        yield Finding("DUE_BEFORE_ISSUE", Severity.WARN, "Due date precedes invoice date")


def confidence(inv: ExtractedInvoice, ctx: ValidationContext) -> Iterable[Finding]:
    if inv.min_confidence() < ctx.min_confidence:
        yield Finding(
            "LOW_CONFIDENCE",
            Severity.BLOCK,
            f"Extraction confidence {inv.min_confidence():.2f} below {ctx.min_confidence:.2f}; needs human check",
        )


DEFAULT_RULES: tuple[Rule, ...] = (
    known_vendor,
    bank_details_match,
    vat_number_matches,
    arithmetic,
    duplicate,
    dates,
    confidence,
)


def validate(inv: ExtractedInvoice, ctx: ValidationContext, rules: Sequence[Rule] = DEFAULT_RULES) -> list[Finding]:
    return [f for rule in rules for f in rule(inv, ctx)]
