"""Demo master data used by the local API and tests."""

from decimal import Decimal

from fwe.domain.models import GoodsReceipt, PurchaseOrder, PurchaseOrderLine, Vendor
from fwe.domain.money import Money

VENDORS = [
    Vendor(id="V-001", name="Acme Office Supplies (Pty) Ltd", vat_number="4123456789", bank_account="62012345678"),
    Vendor(id="V-002", name="Karoo Logistics CC", vat_number="4987654321", bank_account="10098765432"),
]

POS = [
    PurchaseOrder(
        "PO-1001",
        "V-001",
        [
            PurchaseOrderLine("PO-1001-1", "A4 paper box", Decimal("10"), Money.of("450.00")),
            PurchaseOrderLine("PO-1001-2", "Toner cartridge", Decimal("2"), Money.of("1250.00")),
        ],
    ),
]

GRNS = [GoodsReceipt("PO-1001", {"PO-1001-1": Decimal("10"), "PO-1001-2": Decimal("2")})]

SAMPLE_INVOICE = """\
From: Acme Office Supplies (Pty) Ltd
VAT Reg No: 4123456789
Invoice No: ACM-2026-0042
Date: 2026-11-10
Due: 2026-12-10
PO Number: PO-1001

A4 paper box | 10 | R 450.00 | PO-1001-1
Toner cartridge | 2 | R 1,250.00 | PO-1001-2

Subtotal: R 7,000.00
VAT (15%): R 1,050.00
Total due: R 8,050.00
Account No: 62012345678
"""
