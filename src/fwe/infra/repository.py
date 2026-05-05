from __future__ import annotations

from typing import Protocol

from fwe.domain.models import GoodsReceipt, Invoice, InvoiceStatus, PurchaseOrder, Vendor


class Repository(Protocol):
    def save_invoice(self, invoice: Invoice) -> None: ...
    def get_invoice(self, invoice_id: str) -> Invoice | None: ...
    def find_by_source(self, source_ref: str) -> Invoice | None: ...
    def list_invoices(self, status: InvoiceStatus | None = None) -> list[Invoice]: ...
    def find_vendor(self, name: str, vat_number: str | None) -> Vendor | None: ...
    def get_po(self, number: str) -> PurchaseOrder | None: ...
    def get_grn(self, po_number: str) -> GoodsReceipt | None: ...


class InMemoryRepository:
    def __init__(
        self,
        vendors: list[Vendor] | None = None,
        pos: list[PurchaseOrder] | None = None,
        grns: list[GoodsReceipt] | None = None,
    ) -> None:
        self.invoices: dict[str, Invoice] = {}
        self.vendors = {v.id: v for v in vendors or []}
        self.pos = {p.number: p for p in pos or []}
        self.grns = {g.po_number: g for g in grns or []}

    def save_invoice(self, invoice: Invoice) -> None:
        self.invoices[invoice.id] = invoice

    def get_invoice(self, invoice_id: str) -> Invoice | None:
        return self.invoices.get(invoice_id)

    def find_by_source(self, source_ref: str) -> Invoice | None:
        return next((i for i in self.invoices.values() if i.source_ref == source_ref), None)

    def list_invoices(self, status: InvoiceStatus | None = None) -> list[Invoice]:
        items = sorted(self.invoices.values(), key=lambda i: i.received_at)
        return [i for i in items if status is None or i.status == status]

    def find_vendor(self, name: str, vat_number: str | None) -> Vendor | None:
        if vat_number:  # VAT number is the strong key; name is a fallback
            hit = next((v for v in self.vendors.values() if v.vat_number == vat_number), None)
            if hit:
                return hit
        key = name.strip().lower()
        return next((v for v in self.vendors.values() if v.name.lower() == key), None)

    def get_po(self, number: str) -> PurchaseOrder | None:
        return self.pos.get(number)

    def get_grn(self, po_number: str) -> GoodsReceipt | None:
        return self.grns.get(po_number)
