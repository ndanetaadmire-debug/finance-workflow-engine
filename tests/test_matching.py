from decimal import Decimal

from fwe.domain.models import GoodsReceipt
from fwe.extraction.text_extractor import TextInvoiceExtractor
from fwe.infra.seed import POS
from fwe.matching.three_way import MatchPolicy, three_way_match
from tests.conftest import invoice_text

GRN_FULL = GoodsReceipt("PO-1001", {"PO-1001-1": Decimal("10"), "PO-1001-2": Decimal("2")})


def codes(text: str, grn: GoodsReceipt | None = GRN_FULL, policy: MatchPolicy | None = None) -> set[str]:
    inv = TextInvoiceExtractor().extract(text)
    return {f.code for f in three_way_match(inv, POS[0], grn, policy or MatchPolicy())}


def test_perfect_match() -> None:
    assert codes(invoice_text()) == set()


def test_price_variance_respects_tolerance() -> None:
    within = invoice_text(line1="A4 paper box | 10 | R 455.00 | PO-1001-1", subtotal="7,050.00")
    beyond = invoice_text(line1="A4 paper box | 10 | R 470.00 | PO-1001-1", subtotal="7,200.00")
    assert "PRICE_VARIANCE" not in codes(within)
    assert "PRICE_VARIANCE" in codes(beyond)


def test_partial_receipt_and_missing_grn() -> None:
    partial = GoodsReceipt("PO-1001", {"PO-1001-1": Decimal("6"), "PO-1001-2": Decimal("2")})
    assert "QTY_NOT_RECEIVED" in codes(invoice_text(), grn=partial)
    assert "NO_GRN" in codes(invoice_text(), grn=None)


def test_line_not_on_po() -> None:
    text = invoice_text(line2="Gold plated stapler | 2 | R 1,250.00")
    assert "LINE_NOT_ON_PO" in codes(text)
