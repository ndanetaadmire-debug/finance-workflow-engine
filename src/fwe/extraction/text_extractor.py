"""Rule-based extractor over OCR text.

Deliberately simple and deterministic: it is the baseline every ML extractor is
benchmarked against, and the fallback when the ML service is down. Confidence
is lowered whenever a value is inferred instead of read directly.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from fwe.domain.models import ExtractedInvoice, Field, LineItem
from fwe.domain.money import Money
from fwe.extraction.base import ExtractionError

_AMOUNT = r"(?:R|ZAR)?\s*([0-9][0-9 ,]*\.\d{2})"
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d %B %Y", "%d %b %Y")
_LINE = re.compile(
    r"^\s*(?P<desc>[A-Za-z][^|]*?)\s*\|\s*(?P<qty>\d+(?:\.\d+)?)\s*\|\s*(?:R|ZAR)?\s*(?P<price>[0-9][0-9 ,]*\.\d{2})"
    r"(?:\s*\|\s*(?P<ref>PO-\d+-\d+))?\s*$",
    re.MULTILINE,
)


def _money(raw: str, currency: str) -> Money:
    try:
        return Money(Decimal(raw.replace(" ", "").replace(",", "")), currency)
    except InvalidOperation as exc:
        raise ExtractionError(f"unparseable amount {raw!r}") from exc


def _date(raw: str) -> date | None:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _find(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    return m.group(1).strip() if m else None


class TextInvoiceExtractor:
    def __init__(self, default_currency: str = "ZAR") -> None:
        self.currency = default_currency

    def extract(self, text: str) -> ExtractedInvoice:
        currency = _find(r"\bcurrency[:\s]+([A-Z]{3})\b", text) or self.currency

        vendor = _find(r"^\s*(?:from|vendor|supplier)[:\s]+(.+)$", text)
        number = _find(r"\binvoice\s*(?:no\.?|number|#)[:\s]*([A-Z0-9-]+)", text)
        if not vendor or not number:
            raise ExtractionError("vendor name and invoice number are required")

        inv_date_raw = _find(r"\b(?:invoice\s*)?date[:\s]+([0-9A-Za-z /-]+?)\s*$", text)
        inv_date = _date(inv_date_raw) if inv_date_raw else None
        due_raw = _find(r"\bdue(?:\s*date)?[:\s]+([0-9A-Za-z /-]+?)\s*$", text)

        lines = [
            LineItem(
                description=m.group("desc").strip(),
                quantity=Decimal(m.group("qty")),
                unit_price=_money(m.group("price"), currency),
                po_line_ref=m.group("ref"),
            )
            for m in _LINE.finditer(text)
        ]

        subtotal_raw = _find(r"\bsub\s*-?total[:\s]+" + _AMOUNT, text)
        vat_raw = _find(r"\bvat(?:\s*\(?15%\)?)?[:\s]+" + _AMOUNT, text)
        total_raw = _find(r"^\s*(?:total(?:\s*due)?|amount\s*due)[:\s]+" + _AMOUNT, text)

        # Infer missing figures from the ones we have, at reduced confidence.
        subtotal = Field(_money(subtotal_raw, currency), 0.95) if subtotal_raw else None
        vat = Field(_money(vat_raw, currency), 0.95) if vat_raw else None
        total = Field(_money(total_raw, currency), 0.97) if total_raw else None
        if subtotal is None and lines:
            acc = Money(Decimal("0"), currency)
            for li in lines:
                acc = acc + li.total
            subtotal = Field(acc, 0.7)
        if total is None and subtotal and vat:
            total = Field(subtotal.value + vat.value, 0.6)
        if vat is None and total and subtotal:
            vat = Field(total.value - subtotal.value, 0.6)
        if subtotal is None or vat is None or total is None:
            raise ExtractionError("could not determine subtotal, VAT and total")

        return ExtractedInvoice(
            vendor_name=Field(vendor, 0.9),
            vendor_vat_number=Field(
                _find(r"\bvat\s*(?:reg(?:istration)?\s*)?(?:no\.?|number)[:\s]*(4\d{9})", text), 0.9
            ),
            invoice_number=Field(number, 0.95),
            invoice_date=Field(inv_date or date.today(), 0.95 if inv_date else 0.3),
            due_date=Field(_date(due_raw) if due_raw else None, 0.9),
            po_number=Field(_find(r"\b(?:po|purchase\s*order)\s*(?:no\.?|number|#)?[:\s]*(PO-\d+)", text), 0.9),
            bank_account=Field(_find(r"\b(?:account\s*(?:no\.?|number)|acc)[:\s]*(\d{8,12})", text), 0.85),
            subtotal=subtotal,
            vat=vat,
            total=total,
            lines=lines,
        )
