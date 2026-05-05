"""Bank reconciliation: match outgoing bank transactions to approved invoices.

Strategy, cheapest and most certain first:
  1. exact amount + invoice number in the payment reference  → auto-match
  2. exact amount + counterparty resembles vendor             → auto-match
  3. one payment settling several invoices of one vendor      → bounded subset-sum
Anything else is left unmatched for a human. We never force a match.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from itertools import combinations

from fwe.domain.models import BankTransaction
from fwe.domain.money import Money

MAX_BATCH = 6  # combinations grow fast; real payment runs rarely bundle more per vendor


@dataclass(frozen=True, slots=True)
class OpenItem:
    invoice_id: str
    invoice_number: str
    vendor_name: str
    amount: Money


@dataclass(frozen=True, slots=True)
class Match:
    transaction_id: str
    invoice_ids: tuple[str, ...]
    rule: str
    score: float


@dataclass(slots=True)
class ReconciliationResult:
    matches: list[Match] = field(default_factory=list)
    unmatched_transactions: list[str] = field(default_factory=list)
    unmatched_invoices: list[str] = field(default_factory=list)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _name_similarity(a: str, b: str) -> float:
    stop = re.compile(r"\b(pty|ltd|limited|cc|inc|the)\b", re.I)
    return SequenceMatcher(None, _norm(stop.sub("", a)), _norm(stop.sub("", b))).ratio()


def reconcile(transactions: list[BankTransaction], open_items: list[OpenItem]) -> ReconciliationResult:
    result = ReconciliationResult()
    remaining = {i.invoice_id: i for i in open_items}

    for tx in sorted(transactions, key=lambda t: t.booked_on):
        if tx.amount.amount >= 0:
            continue  # only outgoing payments settle payables
        paid = Money(-tx.amount.amount, tx.amount.currency)
        ref = _norm(tx.reference)
        same_amount = [i for i in remaining.values() if i.amount == paid]

        by_ref = [i for i in same_amount if _norm(i.invoice_number) in ref]
        if len(by_ref) == 1:
            result.matches.append(Match(tx.id, (by_ref[0].invoice_id,), "amount+reference", 1.0))
            remaining.pop(by_ref[0].invoice_id)
            continue

        by_name = sorted(
            ((i, _name_similarity(i.vendor_name, tx.counterparty)) for i in same_amount),
            key=lambda x: x[1],
            reverse=True,
        )
        if by_name and by_name[0][1] >= 0.8 and (len(by_name) == 1 or by_name[1][1] < by_name[0][1]):
            item, score = by_name[0]
            result.matches.append(Match(tx.id, (item.invoice_id,), "amount+counterparty", round(score, 2)))
            remaining.pop(item.invoice_id)
            continue

        batch = _find_batch(tx, paid, list(remaining.values()))
        if batch:
            result.matches.append(Match(tx.id, tuple(i.invoice_id for i in batch), "batch-payment", 0.9))
            for i in batch:
                remaining.pop(i.invoice_id)
            continue

        result.unmatched_transactions.append(tx.id)

    result.unmatched_invoices = sorted(remaining)
    return result


def _find_batch(tx: BankTransaction, paid: Money, items: list[OpenItem]) -> list[OpenItem] | None:
    vendor_items = [i for i in items if _name_similarity(i.vendor_name, tx.counterparty) >= 0.8]
    vendor_items = sorted(vendor_items, key=lambda i: i.amount.amount)[: MAX_BATCH * 2]
    for size in range(2, min(MAX_BATCH, len(vendor_items)) + 1):
        hits = [c for c in combinations(vendor_items, size) if sum(i.amount.amount for i in c) == paid.amount]
        if len(hits) == 1:  # ambiguous splits go to a human
            return list(hits[0])
        if len(hits) > 1:
            return None
    return None
