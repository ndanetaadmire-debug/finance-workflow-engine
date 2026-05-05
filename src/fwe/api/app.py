from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

from fwe.domain.models import BankTransaction, Invoice, InvoiceStatus
from fwe.domain.money import Money
from fwe.extraction.text_extractor import TextInvoiceExtractor
from fwe.infra.audit import AuditLog
from fwe.infra.repository import InMemoryRepository
from fwe.infra.seed import GRNS, POS, VENDORS
from fwe.workflow.engine import TransitionError, WorkflowEngine


class IngestRequest(BaseModel):
    document_text: str = Field(min_length=20, max_length=100_000, description="OCR text of the invoice")


class ReviewRequest(BaseModel):
    reviewer: str = Field(min_length=2)
    approve: bool
    note: str = Field(min_length=3, max_length=2000)


class BankLine(BaseModel):
    id: str
    booked_on: date
    amount: Decimal
    currency: str = "ZAR"
    reference: str = ""
    counterparty: str = ""


class FindingOut(BaseModel):
    code: str
    severity: str
    message: str


class InvoiceOut(BaseModel):
    id: str
    status: InvoiceStatus
    vendor_id: str | None
    vendor_name: str | None
    invoice_number: str | None
    total: str | None
    confidence: float | None
    findings: list[FindingOut]
    reviewer: str | None

    @classmethod
    def of(cls, i: Invoice) -> InvoiceOut:
        ex = i.extracted
        return cls(
            id=i.id,
            status=i.status,
            vendor_id=i.vendor_id,
            vendor_name=ex.vendor_name.value if ex else None,
            invoice_number=ex.invoice_number.value if ex else None,
            total=str(ex.total.value) if ex else None,
            confidence=round(ex.min_confidence(), 2) if ex else None,
            findings=[FindingOut(code=f.code, severity=f.severity, message=f.message) for f in i.findings],
            reviewer=i.reviewer,
        )


def get_engine(request: Request) -> WorkflowEngine:
    engine: WorkflowEngine = request.app.state.engine
    return engine


EngineDep = Annotated[WorkflowEngine, Depends(get_engine)]


def create_app(engine: WorkflowEngine | None = None) -> FastAPI:
    audit = AuditLog()
    engine = engine or WorkflowEngine(
        repo=InMemoryRepository(VENDORS, POS, GRNS),
        extractor=TextInvoiceExtractor(),
        audit=audit,
        clock=lambda: datetime.now(UTC),
    )
    app = FastAPI(
        title="Finance Workflow Engine",
        version="1.0.0",
        description="Accounts-payable automation with human-in-the-loop review.",
    )
    app.state.engine = engine

    @app.get("/healthz")
    def health(e: EngineDep) -> dict[str, object]:
        return {"status": "ok", "audit_chain_valid": e.audit.verify()}

    @app.post("/invoices", response_model=InvoiceOut, status_code=201)
    def ingest(body: IngestRequest, e: EngineDep) -> InvoiceOut:
        return InvoiceOut.of(e.ingest(body.document_text, actor="api"))

    @app.get("/invoices", response_model=list[InvoiceOut])
    def list_invoices(e: EngineDep, status: Annotated[InvoiceStatus | None, Query()] = None) -> list[InvoiceOut]:
        return [InvoiceOut.of(i) for i in e.repo.list_invoices(status)]

    @app.get("/invoices/{invoice_id}", response_model=InvoiceOut)
    def get_invoice(invoice_id: str, e: EngineDep) -> InvoiceOut:
        inv = e.repo.get_invoice(invoice_id)
        if inv is None:
            raise HTTPException(404, "invoice not found")
        return InvoiceOut.of(inv)

    @app.get("/invoices/{invoice_id}/audit")
    def audit_trail(invoice_id: str, e: EngineDep) -> list[dict[str, object]]:
        return [
            {"seq": a.seq, "at": a.at, "actor": a.actor, "action": a.action, "data": a.data, "hash": a.hash}
            for a in e.audit.for_entity(invoice_id)
        ]

    @app.post("/invoices/{invoice_id}/review", response_model=InvoiceOut)
    def review(invoice_id: str, body: ReviewRequest, e: EngineDep) -> InvoiceOut:
        try:
            return InvoiceOut.of(e.review(invoice_id, reviewer=body.reviewer, approve=body.approve, note=body.note))
        except KeyError:
            raise HTTPException(404, "invoice not found") from None
        except TransitionError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/reconciliation/run")
    def run_reconciliation(lines: list[BankLine], e: EngineDep) -> dict[str, object]:
        txs = [
            BankTransaction(ln.id, ln.booked_on, Money(ln.amount, ln.currency), ln.reference, ln.counterparty)
            for ln in lines
        ]
        r = e.reconcile(txs, actor="api")
        return {
            "matches": [
                {
                    "transaction_id": m.transaction_id,
                    "invoice_ids": list(m.invoice_ids),
                    "rule": m.rule,
                    "score": m.score,
                }
                for m in r.matches
            ],
            "unmatched_transactions": r.unmatched_transactions,
            "unmatched_invoices": r.unmatched_invoices,
        }

    return app


app = create_app()
