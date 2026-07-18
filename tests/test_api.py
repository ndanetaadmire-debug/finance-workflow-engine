from fastapi.testclient import TestClient

from fwe.api.app import create_app
from fwe.workflow.engine import WorkflowEngine
from tests.conftest import invoice_text


def test_end_to_end_over_http(engine: WorkflowEngine) -> None:
    client = TestClient(create_app(engine))

    ok = client.post("/invoices", json={"document_text": invoice_text()})
    assert ok.status_code == 201
    assert ok.json()["status"] == "approved"

    flagged = client.post("/invoices", json={"document_text": invoice_text(number="ACM-9", account="00000000000")})
    body = flagged.json()
    assert body["status"] == "needs_review"
    assert any(f["code"] == "BANK_DETAILS_CHANGED" for f in body["findings"])

    queue = client.get("/invoices", params={"status": "needs_review"}).json()
    assert [i["id"] for i in queue] == [body["id"]]

    reviewed = client.post(
        f"/invoices/{body['id']}/review", json={"reviewer": "lead", "approve": True, "note": "verified"}
    )
    assert reviewed.json()["status"] == "approved"
    conflict = client.post(
        f"/invoices/{body['id']}/review", json={"reviewer": "lead", "approve": True, "note": "again"}
    )
    assert conflict.status_code == 409

    recon = client.post(
        "/reconciliation/run",
        json=[
            {"id": "T1", "booked_on": "2026-11-20", "amount": "-8050.00", "reference": "ACM-2026-0042"},
        ],
    ).json()
    assert len(recon["matches"]) == 1

    trail = client.get(f"/invoices/{ok.json()['id']}/audit").json()
    assert trail[-1]["action"] == "approved→paid"
    assert client.get("/healthz").json() == {"status": "ok", "audit_chain_valid": True}
    assert client.get("/invoices/nope").status_code == 404
