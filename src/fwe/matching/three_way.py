"""Three-way match: invoice ↔ purchase order ↔ goods received note.

Pay only for what was ordered, at the ordered price, and actually received.
Tolerances are policy, passed in, never hard-coded at call sites.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from fwe.domain.models import ExtractedInvoice, Finding, GoodsReceipt, PurchaseOrder, Severity


@dataclass(frozen=True, slots=True)
class MatchPolicy:
    price_tolerance_pct: Decimal = Decimal("0.02")
    allow_over_receipt: bool = False


def three_way_match(
    inv: ExtractedInvoice,
    po: PurchaseOrder | None,
    grn: GoodsReceipt | None,
    policy: MatchPolicy = MatchPolicy(),
) -> list[Finding]:
    if inv.po_number.value is None:
        return [Finding("NO_PO", Severity.WARN, "Non-PO invoice; requires budget-holder approval")]
    if po is None:
        return [Finding("PO_NOT_FOUND", Severity.BLOCK, f"PO {inv.po_number.value} not found")]

    findings: list[Finding] = []
    po_lines = {line.ref: line for line in po.lines}
    received = grn.received if grn else {}
    if grn is None:
        findings.append(Finding("NO_GRN", Severity.BLOCK, f"No goods receipt recorded for {po.number}"))

    for li in inv.lines:
        ref = li.po_line_ref
        if ref is None or ref not in po_lines:
            findings.append(Finding("LINE_NOT_ON_PO", Severity.BLOCK, f"'{li.description}' is not on {po.number}"))
            continue
        pol = po_lines[ref]
        if not li.unit_price.within(pol.unit_price, pct=policy.price_tolerance_pct):
            findings.append(
                Finding(
                    "PRICE_VARIANCE",
                    Severity.BLOCK,
                    f"{ref}: invoiced {li.unit_price} vs PO {pol.unit_price} (> {policy.price_tolerance_pct:%})",
                )
            )
        if li.quantity > pol.quantity:
            findings.append(
                Finding("QTY_OVER_PO", Severity.BLOCK, f"{ref}: invoiced {li.quantity} > ordered {pol.quantity}")
            )
        if grn is not None:
            got = received.get(ref, Decimal("0"))
            if li.quantity > got and not policy.allow_over_receipt:
                findings.append(
                    Finding("QTY_NOT_RECEIVED", Severity.BLOCK, f"{ref}: invoiced {li.quantity} > received {got}")
                )
    return findings
