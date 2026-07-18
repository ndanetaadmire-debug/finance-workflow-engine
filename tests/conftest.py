from datetime import UTC, datetime

import pytest

from fwe.extraction.text_extractor import TextInvoiceExtractor
from fwe.infra.audit import AuditLog
from fwe.infra.repository import InMemoryRepository
from fwe.infra.seed import GRNS, POS, VENDORS
from fwe.workflow.engine import WorkflowEngine

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)


@pytest.fixture
def engine() -> WorkflowEngine:
    return WorkflowEngine(
        repo=InMemoryRepository(list(VENDORS), list(POS), list(GRNS)),
        extractor=TextInvoiceExtractor(),
        audit=AuditLog(),
        clock=lambda: NOW,
    )


def invoice_text(**overrides: str) -> str:
    v = {
        "vendor": "Acme Office Supplies (Pty) Ltd",
        "vat_no": "4123456789",
        "number": "ACM-2026-0042",
        "date": "2026-11-10",
        "po": "PO-1001",
        "line1": "A4 paper box | 10 | R 450.00 | PO-1001-1",
        "line2": "Toner cartridge | 2 | R 1,250.00 | PO-1001-2",
        "subtotal": "7,000.00",
        "vat": "1,050.00",
        "total": "8,050.00",
        "account": "62012345678",
    } | overrides
    return (
        f"From: {v['vendor']}\nVAT Reg No: {v['vat_no']}\nInvoice No: {v['number']}\nDate: {v['date']}\n"
        f"Due: 2026-12-10\nPO Number: {v['po']}\n\n{v['line1']}\n{v['line2']}\n\n"
        f"Subtotal: R {v['subtotal']}\nVAT (15%): R {v['vat']}\nTotal due: R {v['total']}\nAccount No: {v['account']}\n"
    )
