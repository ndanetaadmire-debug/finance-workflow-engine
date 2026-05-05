-- Finance Workflow Engine: PostgreSQL schema
-- Money is NUMERIC(18,2) + ISO currency. Never FLOAT.

CREATE TYPE invoice_status AS ENUM (
  'received', 'extracted', 'validated', 'matched', 'needs_review', 'approved', 'rejected', 'paid'
);

CREATE TABLE vendors (
  id                  TEXT PRIMARY KEY,
  name                TEXT NOT NULL,
  vat_number          TEXT UNIQUE,
  bank_account        TEXT NOT NULL,
  payment_terms_days  INT  NOT NULL DEFAULT 30,
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE invoices (
  id              TEXT PRIMARY KEY,
  source_ref      TEXT NOT NULL UNIQUE,              -- sha256 of document: idempotent ingestion
  vendor_id       TEXT REFERENCES vendors(id),
  invoice_number  TEXT,
  invoice_date    DATE,
  po_number       TEXT,
  currency        CHAR(3) NOT NULL DEFAULT 'ZAR',
  subtotal        NUMERIC(18,2),
  vat             NUMERIC(18,2),
  total           NUMERIC(18,2),
  min_confidence  REAL,
  status          invoice_status NOT NULL DEFAULT 'received',
  reviewer        TEXT,
  received_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  version         INT NOT NULL DEFAULT 0              -- optimistic concurrency for reviewers
);

-- Hard duplicate guard at the database level, normalising the invoice number.
CREATE UNIQUE INDEX invoices_vendor_number_uq
  ON invoices (vendor_id, upper(regexp_replace(invoice_number, '[^A-Za-z0-9]', '', 'g')))
  WHERE status <> 'rejected';

CREATE INDEX invoices_review_queue ON invoices (received_at) WHERE status = 'needs_review';

CREATE TABLE invoice_findings (
  invoice_id  TEXT NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
  code        TEXT NOT NULL,
  severity    TEXT NOT NULL CHECK (severity IN ('info','warn','block')),
  message     TEXT NOT NULL,
  PRIMARY KEY (invoice_id, code)
);

-- Tamper-evident audit chain. Application role gets INSERT/SELECT only.
CREATE TABLE audit_log (
  seq        BIGINT PRIMARY KEY,
  at         TIMESTAMPTZ NOT NULL,
  actor      TEXT NOT NULL,
  entity_id  TEXT NOT NULL,
  action     TEXT NOT NULL,
  data       JSONB NOT NULL DEFAULT '{}',
  prev_hash  CHAR(64) NOT NULL,
  hash       CHAR(64) NOT NULL UNIQUE
);
CREATE INDEX audit_log_entity ON audit_log (entity_id, seq);

CREATE ROLE fwe_app NOLOGIN;
GRANT SELECT, INSERT, UPDATE ON vendors, invoices, invoice_findings TO fwe_app;
GRANT SELECT, INSERT ON audit_log TO fwe_app;
REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM fwe_app;
