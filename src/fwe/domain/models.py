from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from fwe.domain.money import Money


class InvoiceStatus(StrEnum):
    RECEIVED = "received"
    EXTRACTED = "extracted"
    VALIDATED = "validated"
    MATCHED = "matched"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PAID = "paid"


@dataclass(frozen=True, slots=True)
class Field[T]:
    """An extracted value with the extractor's confidence (0..1)."""

    value: T
    confidence: float


@dataclass(slots=True)
class LineItem:
    description: str
    quantity: Decimal
    unit_price: Money
    po_line_ref: str | None = None

    @property
    def total(self) -> Money:
        return self.unit_price * self.quantity


@dataclass(slots=True)
class ExtractedInvoice:
    vendor_name: Field[str]
    vendor_vat_number: Field[str | None]
    invoice_number: Field[str]
    invoice_date: Field[date]
    due_date: Field[date | None]
    po_number: Field[str | None]
    bank_account: Field[str | None]
    subtotal: Field[Money]
    vat: Field[Money]
    total: Field[Money]
    lines: list[LineItem]

    def min_confidence(self) -> float:
        fields = (
            self.vendor_name,
            self.invoice_number,
            self.invoice_date,
            self.subtotal,
            self.vat,
            self.total,
        )
        return min(f.confidence for f in fields)


@dataclass(slots=True)
class Vendor:
    id: str
    name: str
    vat_number: str | None
    bank_account: str
    payment_terms_days: int = 30


@dataclass(slots=True)
class PurchaseOrderLine:
    ref: str
    description: str
    quantity: Decimal
    unit_price: Money


@dataclass(slots=True)
class PurchaseOrder:
    number: str
    vendor_id: str
    lines: list[PurchaseOrderLine]


@dataclass(slots=True)
class GoodsReceipt:
    po_number: str
    received: dict[str, Decimal]  # po_line_ref -> quantity received


class Severity(StrEnum):
    INFO = "info"
    WARN = "warn"
    BLOCK = "block"


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    severity: Severity
    message: str


@dataclass(slots=True)
class Invoice:
    id: str
    source_ref: str
    received_at: datetime
    status: InvoiceStatus = InvoiceStatus.RECEIVED
    extracted: ExtractedInvoice | None = None
    vendor_id: str | None = None
    findings: list[Finding] = field(default_factory=list)
    reviewer: str | None = None

    @property
    def total(self) -> Money | None:
        return self.extracted.total.value if self.extracted else None


@dataclass(frozen=True, slots=True)
class BankTransaction:
    id: str
    booked_on: date
    amount: Money  # negative = outgoing payment
    reference: str
    counterparty: str
