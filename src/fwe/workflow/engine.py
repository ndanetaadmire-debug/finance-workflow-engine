"""The AP workflow: a small explicit state machine with an audit entry per transition.

    RECEIVED → EXTRACTED → VALIDATED → MATCHED → APPROVED → PAID
         ↘          ↘           ↘          ↘
                       NEEDS_REVIEW  ──(human)──▶ APPROVED | REJECTED

Straight-through processing happens only when every check passes with no BLOCK
findings and the amount is under the auto-approval limit. Everything else waits
for a person, with the reasons attached.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from fwe.domain.models import BankTransaction, Finding, Invoice, InvoiceStatus, Severity
from fwe.extraction.base import ExtractionError, Extractor
from fwe.infra.audit import AuditLog
from fwe.infra.repository import Repository
from fwe.matching.three_way import MatchPolicy, three_way_match
from fwe.reconciliation.matcher import OpenItem, ReconciliationResult, reconcile
from fwe.validation.rules import ValidationContext, validate

ALLOWED: dict[InvoiceStatus, set[InvoiceStatus]] = {
    InvoiceStatus.RECEIVED: {InvoiceStatus.EXTRACTED, InvoiceStatus.NEEDS_REVIEW},
    InvoiceStatus.EXTRACTED: {InvoiceStatus.VALIDATED, InvoiceStatus.NEEDS_REVIEW},
    InvoiceStatus.VALIDATED: {InvoiceStatus.MATCHED, InvoiceStatus.NEEDS_REVIEW},
    InvoiceStatus.MATCHED: {InvoiceStatus.APPROVED, InvoiceStatus.NEEDS_REVIEW},
    InvoiceStatus.NEEDS_REVIEW: {InvoiceStatus.APPROVED, InvoiceStatus.REJECTED},
    InvoiceStatus.APPROVED: {InvoiceStatus.PAID},
    InvoiceStatus.REJECTED: set(),
    InvoiceStatus.PAID: set(),
}


class TransitionError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class EnginePolicy:
    auto_approve_limit: Decimal = Decimal("50000.00")
    min_confidence: float = 0.8
    match: MatchPolicy = field(default_factory=MatchPolicy)


class WorkflowEngine:
    def __init__(
        self,
        repo: Repository,
        extractor: Extractor,
        audit: AuditLog,
        clock: Callable[[], datetime],
        policy: EnginePolicy = EnginePolicy(),
    ) -> None:
        self.repo, self.extractor, self.audit, self.clock, self.policy = repo, extractor, audit, clock, policy

    # ---- ingestion -------------------------------------------------------------------------
    def ingest(self, document_text: str, *, actor: str = "system") -> Invoice:
        """Idempotent: the same document (by content hash) is processed once."""
        source_ref = "sha256:" + hashlib.sha256(document_text.encode()).hexdigest()
        if existing := self.repo.find_by_source(source_ref):
            return existing

        inv = Invoice(id=f"INV-{source_ref[7:19].upper()}", source_ref=source_ref, received_at=self.clock())
        self.repo.save_invoice(inv)
        self._log(inv, actor, "received")

        try:
            inv.extracted = self.extractor.extract(document_text)
        except ExtractionError as exc:
            return self._to_review(inv, [Finding("EXTRACTION_FAILED", Severity.BLOCK, str(exc))], actor)
        self._transition(inv, InvoiceStatus.EXTRACTED, actor, {"confidence": inv.extracted.min_confidence()})

        ex = inv.extracted
        vendor = self.repo.find_vendor(ex.vendor_name.value, ex.vendor_vat_number.value)
        inv.vendor_id = vendor.id if vendor else None
        prior = [
            (i.vendor_id, i.extracted.invoice_number.value, i.extracted.total.value)
            for i in self.repo.list_invoices()
            if i.id != inv.id and i.vendor_id and i.extracted and i.status != InvoiceStatus.REJECTED
        ]
        ctx = ValidationContext(
            vendor=vendor, today=self.clock().date(), prior_invoices=prior, min_confidence=self.policy.min_confidence
        )
        findings = validate(ex, ctx)
        inv.findings.extend(findings)
        if _blocked(findings):
            return self._to_review(inv, [], actor)
        self._transition(inv, InvoiceStatus.VALIDATED, actor)

        po = self.repo.get_po(ex.po_number.value) if ex.po_number.value else None
        grn = self.repo.get_grn(po.number) if po else None
        match_findings = three_way_match(ex, po, grn, self.policy.match)
        inv.findings.extend(match_findings)
        if _blocked(match_findings) or (ex.po_number.value is None):
            return self._to_review(inv, [], actor)
        self._transition(inv, InvoiceStatus.MATCHED, actor)

        if ex.total.value.amount > self.policy.auto_approve_limit:
            return self._to_review(
                inv,
                [Finding("OVER_LIMIT", Severity.BLOCK, f"Above auto-approval limit {self.policy.auto_approve_limit}")],
                actor,
            )
        self._transition(inv, InvoiceStatus.APPROVED, actor, {"mode": "straight-through"})
        return inv

    # ---- human in the loop -----------------------------------------------------------------
    def review(self, invoice_id: str, *, reviewer: str, approve: bool, note: str) -> Invoice:
        inv = self._get(invoice_id)
        if inv.status != InvoiceStatus.NEEDS_REVIEW:
            raise TransitionError(f"{invoice_id} is {inv.status}, not awaiting review")
        if not note.strip():
            raise ValueError("A review note is required for the audit trail")
        inv.reviewer = reviewer
        self._transition(inv, InvoiceStatus.APPROVED if approve else InvoiceStatus.REJECTED, reviewer, {"note": note})
        return inv

    # ---- payments --------------------------------------------------------------------------
    def reconcile(self, transactions: list[BankTransaction], *, actor: str = "system") -> ReconciliationResult:
        approved = self.repo.list_invoices(InvoiceStatus.APPROVED)
        items = [
            OpenItem(i.id, i.extracted.invoice_number.value, i.extracted.vendor_name.value, i.extracted.total.value)
            for i in approved
            if i.extracted
        ]
        result = reconcile(transactions, items)
        for m in result.matches:
            for inv_id in m.invoice_ids:
                self._transition(
                    self._get(inv_id),
                    InvoiceStatus.PAID,
                    actor,
                    {"transaction": m.transaction_id, "rule": m.rule, "score": m.score},
                )
        return result

    # ---- internals -------------------------------------------------------------------------
    def _get(self, invoice_id: str) -> Invoice:
        inv = self.repo.get_invoice(invoice_id)
        if inv is None:
            raise KeyError(invoice_id)
        return inv

    def _to_review(self, inv: Invoice, extra: list[Finding], actor: str) -> Invoice:
        inv.findings.extend(extra)
        codes = [f.code for f in inv.findings if f.severity == Severity.BLOCK]
        self._transition(inv, InvoiceStatus.NEEDS_REVIEW, actor, {"reasons": codes})
        return inv

    def _transition(self, inv: Invoice, to: InvoiceStatus, actor: str, data: dict[str, object] | None = None) -> None:
        if to not in ALLOWED[inv.status]:
            raise TransitionError(f"{inv.status} → {to} is not allowed")
        frm, inv.status = inv.status, to
        self.repo.save_invoice(inv)
        self._log(inv, actor, f"{frm}→{to}", data)

    def _log(self, inv: Invoice, actor: str, action: str, data: dict[str, object] | None = None) -> None:
        self.audit.record(actor=actor, entity_id=inv.id, action=action, at=self.clock(), data=dict(data or {}))


def _blocked(findings: list[Finding]) -> bool:
    return any(f.severity == Severity.BLOCK for f in findings)
