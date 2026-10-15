# finance-workflow-engine

[![CI](https://github.com/ndanetaadmire-debug/finance-workflow-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/ndanetaadmire-debug/finance-workflow-engine/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13-3776AB?logo=python&logoColor=white)
![mypy](https://img.shields.io/badge/mypy-strict-2A6DB2)
![Coverage](https://img.shields.io/badge/coverage-92%25-brightgreen)
![License](https://img.shields.io/badge/license-MIT-blue)

**Accounts-payable automation that a finance controller would actually sign off on.** Invoices are extracted, validated, three-way matched against purchase orders and goods receipts, approved straight-through when safe, and reconciled against bank statements. Anything uncertain goes to a human with the reasons attached — and every step lands in a tamper-evident audit chain.

```
POST /invoices  ──▶ RECEIVED ─▶ EXTRACTED ─▶ VALIDATED ─▶ MATCHED ─▶ APPROVED ─▶ PAID
                       │            │            │           │           ▲
                       └────────────┴────────────┴───────────┴─▶ NEEDS_REVIEW ──(human + note)──▶ APPROVED | REJECTED
```

## What it catches

| Check | Why it matters | Severity |
|---|---|---|
| **Bank details differ from vendor master** | The most common AP fraud (business email compromise) | block |
| VAT number mismatch | Wrong or spoofed supplier | block |
| Subtotal + VAT ≠ total · lines ≠ subtotal | Keying and OCR errors | block |
| VAT ≠ 15% of subtotal | SA VAT compliance | warn |
| **Duplicate** (normalised `ACM-0042` ≡ `acm0042`) / same-amount repeat | Paying twice | block / warn |
| Future-dated or > 12 months old | Policy | block / warn |
| **3-way match**: price variance > 2%, qty > PO, qty > received, line not on PO, no GRN | Pay only for what was ordered and delivered | block |
| Extraction confidence < 0.8 | Never trust a guess with money | block |
| Total above auto-approval limit | Segregation of duties | block |

## Design highlights

- **Explicit state machine** with an allowed-transitions table. Illegal moves raise; there is no "just set the status".
- **Idempotent ingestion** keyed on the document's SHA-256, plus a database-level unique index on the normalised vendor + invoice number.
- **Money is `Decimal` + currency**, rounded half-up to cents. Mixing currencies raises. Floats are rejected at construction.
- **Rules are pure functions** `(invoice, context) → findings`: small, ordered, individually tested, easy to add.
- **Extractor is a port.** The rule-based OCR-text extractor is the deterministic baseline and fallback; Azure Document Intelligence, Textract or an LLM with structured output plug in behind the same `Protocol`, each returning per-field confidence.
- **Bank reconciliation never forces a match**: amount + reference → amount + fuzzy counterparty → bounded subset-sum for batch payments. Ambiguity goes to a person.
- **Hash-chained audit log**: each entry commits to the previous hash; `verify()` detects any edit or deletion. In Postgres the app role is `INSERT`/`SELECT` only on that table.
- **Human review requires a note** and is only possible from `NEEDS_REVIEW`; double-approval returns `409`.

## Layout

```
src/fwe/
  domain/          Money, Invoice, Vendor, PO, GRN, findings
  extraction/      Extractor port + rule-based OCR text extractor with confidence
  validation/      Pure validation rules
  matching/        Three-way match with tolerance policy
  reconciliation/  Bank statement matcher (reference, counterparty, batch)
  workflow/        State machine, straight-through vs human review
  infra/           Repository, hash-chained audit log, demo seed data
  api/             FastAPI app
migrations/        PostgreSQL schema (enum states, partial indexes, append-only audit)
tests/             28 tests, 92% branch coverage
```

## Run it

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
uvicorn fwe.api.app:app --reload        # http://localhost:8000/docs

pytest --cov && ruff check src tests && mypy
```

```bash
curl -s localhost:8000/invoices -H 'content-type: application/json' \
  -d "$(python -c 'import json,fwe.infra.seed as s;print(json.dumps({"document_text":s.SAMPLE_INVOICE}))')"
# → {"status":"approved", "findings":[], ...}
```

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/invoices` | Ingest OCR text; runs the full pipeline |
| `GET` | `/invoices?status=needs_review` | Review queue |
| `GET` | `/invoices/{id}` · `/invoices/{id}/audit` | Detail and audit trail |
| `POST` | `/invoices/{id}/review` | Approve / reject with a mandatory note |
| `POST` | `/reconciliation/run` | Match bank lines to approved invoices; marks them paid |
| `GET` | `/healthz` | Liveness + audit chain integrity |

See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** and **[docs/adr](docs/adr)**.

---

Built by **[Admire T. Ndaneta](https://admire-portfolio.vercel.app)** — senior full-stack & AI engineer. MIT licensed.
