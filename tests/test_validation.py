from datetime import date

from fwe.domain.money import Money
from fwe.extraction.text_extractor import TextInvoiceExtractor
from fwe.infra.seed import VENDORS
from fwe.validation.rules import ValidationContext, validate
from tests.conftest import invoice_text

TODAY = date(2026, 11, 13)


def codes(text: str, *, prior: list[tuple[str, str, Money]] | None = None, vendor: bool = True) -> set[str]:
    inv = TextInvoiceExtractor().extract(text)
    ctx = ValidationContext(vendor=VENDORS[0] if vendor else None, today=TODAY, prior_invoices=prior or [])
    return {f.code for f in validate(inv, ctx)}


def test_clean_invoice_passes() -> None:
    assert codes(invoice_text()) == set()


def test_bank_detail_change_is_blocked() -> None:
    assert "BANK_DETAILS_CHANGED" in codes(invoice_text(account="99999999999"))


def test_arithmetic_errors() -> None:
    assert "TOTAL_MISMATCH" in codes(invoice_text(total="8,500.00"))
    assert "VAT_RATE" in codes(invoice_text(vat="1,400.00", total="8,400.00"))
    assert "LINES_MISMATCH" in codes(invoice_text(line1="A4 paper box | 12 | R 450.00 | PO-1001-1"))


def test_duplicates_normalise_invoice_numbers() -> None:
    prior = [("V-001", "acm20260042", Money.of("1.00"))]
    assert "DUPLICATE" in codes(invoice_text(), prior=prior)
    assert "POSSIBLE_DUPLICATE" in codes(invoice_text(), prior=[("V-001", "OTHER-1", Money.of("8050.00"))])


def test_dates_and_unknown_vendor() -> None:
    assert "FUTURE_DATED" in codes(invoice_text(date="2027-01-01"))
    assert "STALE" in codes(invoice_text(date="2025-01-01"))
    assert "VENDOR_UNKNOWN" in codes(invoice_text(), vendor=False)
