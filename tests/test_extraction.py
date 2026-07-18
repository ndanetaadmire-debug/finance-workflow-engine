from datetime import date
from decimal import Decimal

import pytest

from fwe.domain.money import Money
from fwe.extraction.base import ExtractionError
from fwe.extraction.text_extractor import TextInvoiceExtractor
from tests.conftest import invoice_text


def test_extracts_all_fields() -> None:
    inv = TextInvoiceExtractor().extract(invoice_text())
    assert inv.vendor_name.value == "Acme Office Supplies (Pty) Ltd"
    assert inv.invoice_number.value == "ACM-2026-0042"
    assert inv.invoice_date.value == date(2026, 11, 10)
    assert inv.po_number.value == "PO-1001"
    assert inv.total.value == Money.of("8050.00")
    assert [li.po_line_ref for li in inv.lines] == ["PO-1001-1", "PO-1001-2"]
    assert inv.lines[1].unit_price.amount == Decimal("1250.00")
    assert inv.min_confidence() >= 0.9


def test_infers_missing_total_with_lower_confidence() -> None:
    text = invoice_text().replace("Total due: R 8,050.00\n", "")
    inv = TextInvoiceExtractor().extract(text)
    assert inv.total.value == Money.of("8050.00")
    assert inv.total.confidence < 0.8


def test_rejects_documents_without_identity() -> None:
    with pytest.raises(ExtractionError):
        TextInvoiceExtractor().extract("Hello, please pay R100")
