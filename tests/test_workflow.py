from dataclasses import replace
from datetime import date

import pytest

from fwe.domain.models import BankTransaction, InvoiceStatus
from fwe.domain.money import Money
from fwe.workflow.engine import TransitionError, WorkflowEngine
from tests.conftest import invoice_text


def test_clean_invoice_goes_straight_through(engine: WorkflowEngine) -> None:
    inv = engine.ingest(invoice_text())
    assert inv.status == InvoiceStatus.APPROVED
    actions = [e.action for e in engine.audit.for_entity(inv.id)]
    assert actions == ["received", "received→extracted", "extracted→validated", "validated→matched", "matched→approved"]


def test_ingest_is_idempotent(engine: WorkflowEngine) -> None:
    a, b = engine.ingest(invoice_text()), engine.ingest(invoice_text())
    assert a.id == b.id
    assert len(engine.repo.list_invoices()) == 1


def test_second_copy_with_new_layout_is_caught_as_duplicate(engine: WorkflowEngine) -> None:
    engine.ingest(invoice_text())
    dup = engine.ingest(invoice_text() + "\nThank you for your business!")
    assert dup.status == InvoiceStatus.NEEDS_REVIEW
    assert "DUPLICATE" in {f.code for f in dup.findings}


def test_fraud_signal_routes_to_human_then_review_resolves(engine: WorkflowEngine) -> None:
    inv = engine.ingest(invoice_text(account="11122233344"))
    assert inv.status == InvoiceStatus.NEEDS_REVIEW
    with pytest.raises(ValueError):
        engine.review(inv.id, reviewer="thandi", approve=False, note="  ")
    engine.review(inv.id, reviewer="thandi", approve=False, note="Called Acme: bank change not genuine")
    assert inv.status == InvoiceStatus.REJECTED
    with pytest.raises(TransitionError):
        engine.review(inv.id, reviewer="thandi", approve=True, note="changed my mind")


def test_over_limit_requires_approval(engine: WorkflowEngine) -> None:
    text = invoice_text(
        line1="A4 paper box | 10 | R 450.00 | PO-1001-1",
        line2="Toner cartridge | 2 | R 1,250.00 | PO-1001-2",
    )
    engine.policy = type(engine.policy)(auto_approve_limit=engine.policy.auto_approve_limit / 10)
    inv = engine.ingest(text)
    assert inv.status == InvoiceStatus.NEEDS_REVIEW
    assert "OVER_LIMIT" in {f.code for f in inv.findings}


def test_unparseable_document_goes_to_review(engine: WorkflowEngine) -> None:
    inv = engine.ingest("this is a menu from a restaurant, not an invoice at all")
    assert inv.status == InvoiceStatus.NEEDS_REVIEW
    assert inv.findings[0].code == "EXTRACTION_FAILED"


def test_reconciliation_marks_paid_and_audit_chain_holds(engine: WorkflowEngine) -> None:
    inv = engine.ingest(invoice_text())
    result = engine.reconcile([BankTransaction("T1", date(2026, 11, 20), Money.of("-8050.00"), "ACM-2026-0042", "")])
    assert result.matches[0].invoice_ids == (inv.id,)
    assert inv.status == InvoiceStatus.PAID
    assert engine.audit.verify()


def test_audit_tampering_is_detected(engine: WorkflowEngine) -> None:
    engine.ingest(invoice_text())
    assert engine.audit.verify()
    entries = engine.audit._entries
    entries[2] = replace(entries[2], actor="mallory")  # rewrite history without re-hashing
    assert not engine.audit.verify()
