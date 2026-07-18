from datetime import date

from fwe.domain.models import BankTransaction
from fwe.domain.money import Money
from fwe.reconciliation.matcher import OpenItem, reconcile

ITEMS = [
    OpenItem("INV-A", "ACM-0042", "Acme Office Supplies (Pty) Ltd", Money.of("8050.00")),
    OpenItem("INV-B", "KL-881", "Karoo Logistics CC", Money.of("1200.00")),
    OpenItem("INV-C", "KL-882", "Karoo Logistics CC", Money.of("800.00")),
    OpenItem("INV-D", "ACM-0043", "Acme Office Supplies (Pty) Ltd", Money.of("999.99")),
]


def tx(id_: str, amount: str, ref: str = "", cp: str = "") -> BankTransaction:
    return BankTransaction(id_, date(2026, 11, 20), Money.of(amount), ref, cp)


def test_matches_by_amount_and_reference() -> None:
    r = reconcile([tx("T1", "-8050.00", ref="PMT ACM0042")], ITEMS)
    assert r.matches[0].invoice_ids == ("INV-A",)
    assert r.matches[0].rule == "amount+reference"


def test_matches_by_counterparty_name() -> None:
    r = reconcile([tx("T1", "-999.99", cp="ACME OFFICE SUPPLIES")], ITEMS)
    assert r.matches[0].invoice_ids == ("INV-D",)


def test_batch_payment_settles_multiple_invoices() -> None:
    r = reconcile([tx("T1", "-2000.00", cp="Karoo Logistics")], ITEMS)
    assert r.matches[0].rule == "batch-payment"
    assert set(r.matches[0].invoice_ids) == {"INV-B", "INV-C"}


def test_never_forces_a_match() -> None:
    r = reconcile([tx("T1", "-123.45", cp="Unknown"), tx("T2", "500.00", cp="Refund in")], ITEMS)
    assert r.matches == []
    assert r.unmatched_transactions == ["T1"]  # incoming credits are ignored
    assert len(r.unmatched_invoices) == 4
