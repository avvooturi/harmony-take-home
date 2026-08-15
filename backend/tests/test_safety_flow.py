from sqlalchemy import select

from app.connectors.erp import ERPConnector, VersionConflict
from app.db import SessionLocal
from app.models import AuditEvent, PurchaseOrder


def create_approval(client, headers):
    response = client.post("/api/proactive/run", headers=headers)
    assert response.status_code == 200
    approval = client.get("/api/approvals", headers=headers).json()[0]
    return approval


def test_unauthorized_employee_cannot_access_purchase_order(client, floor_headers):
    response = client.get("/api/erp/purchase-orders/PO-1007", headers=floor_headers)
    assert response.status_code == 403


def test_unauthorized_employee_cannot_invoke_restricted_tool(client, floor_headers):
    response = client.post("/api/tools/invoke", headers=floor_headers,
        json={"name": "get_inventory", "arguments": {"part_id": "PART-X"}})
    assert response.status_code == 403


def test_write_cannot_execute_without_approval(client, pm_headers):
    response = client.post("/api/tools/invoke", headers=pm_headers, json={
        "name": "change_purchase_order_supplier",
        "arguments": {"po_id": "PO-1007", "supplier_id": "SUP-Z", "expected_version": 1, "key": "no-approval"}})
    assert response.status_code == 409
    with SessionLocal() as db:
        assert db.get(PurchaseOrder, "PO-1007").supplier_id == "SUP-Y"


def test_rejected_action_does_not_mutate(client, pm_headers):
    approval = create_approval(client, pm_headers)
    response = client.post(f"/api/approvals/{approval['id']}/decision", headers=pm_headers, json={"decision": "REJECT"})
    assert response.json()["status"] == "REJECTED"
    with SessionLocal() as db:
        assert db.get(PurchaseOrder, "PO-1007").supplier_id == "SUP-Y"


def test_approved_action_mutates_once_and_is_audited(client, pm_headers):
    approval = create_approval(client, pm_headers)
    before = client.get("/api/erp/purchase-orders/PO-1007", headers=pm_headers).json()
    assert before["supplier_id"] == "SUP-Y"
    response = client.post(f"/api/approvals/{approval['id']}/decision", headers=pm_headers, json={"decision": "APPROVE"})
    assert response.status_code == 200
    assert response.json()["verified"]["supplier_id"] == "SUP-Z"
    second = client.post(f"/api/approvals/{approval['id']}/decision", headers=pm_headers, json={"decision": "APPROVE"})
    assert second.json()["message"] == "Decision already recorded"
    with SessionLocal() as db:
        po = db.get(PurchaseOrder, "PO-1007")
        assert po.version == 2
        assert db.scalar(select(AuditEvent).where(AuditEvent.event_type == "ACTION_EXECUTED"))


def test_duplicate_idempotency_key_does_not_repeat_mutation():
    with SessionLocal() as db:
        erp = ERPConnector(db)
        first = erp.change_supplier("PO-1007", "SUP-Z", 1, "same-key")
        second = erp.change_supplier("PO-1007", "SUP-Z", 1, "same-key")
        assert not first["idempotent_replay"] and second["idempotent_replay"]
        assert db.get(PurchaseOrder, "PO-1007").version == 2


def test_stale_version_fails_safely():
    with SessionLocal() as db:
        erp = ERPConnector(db)
        erp.change_supplier("PO-1007", "SUP-Z", 1, "first")
        try:
            erp.change_supplier("PO-1007", "SUP-Y", 1, "stale")
            assert False, "expected conflict"
        except VersionConflict:
            pass
        assert db.get(PurchaseOrder, "PO-1007").supplier_id == "SUP-Z"


def test_proactive_scenario_creates_correct_alert(client, pm_headers):
    response = client.post("/api/proactive/run", headers=pm_headers)
    assert response.status_code == 200
    alert = response.json()[0]
    assert alert["priority"] == "HIGH"
    assert "4812" in alert["title"]
    assert any("Tuesday" in evidence for evidence in alert["evidence"])


def test_floor_employee_cannot_trigger_purchasing_analysis(client, floor_headers):
    assert client.post("/api/proactive/run", headers=floor_headers).status_code == 403
