from sqlalchemy import func, select

from app.config import settings
from app.db import SessionLocal
from app.models import (AgentRun, AgentStep, ApprovalRequest, AttentionItem, AuditEvent,
                        IdempotencyRecord, Memory, PurchaseOrder)


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_demo_reset_restores_seed_and_scenario_can_run_again(client, pm_headers):
    proactive = client.post("/api/proactive/run", headers=pm_headers)
    assert proactive.status_code == 200
    approval = client.get("/api/approvals", headers=pm_headers).json()[0]
    executed = client.post(f"/api/approvals/{approval['id']}/decision",
                           headers=pm_headers, json={"decision": "APPROVE"})
    assert executed.status_code == 200

    with SessionLocal() as db:
        changed = db.get(PurchaseOrder, "PO-1007")
        assert changed.supplier_id == "SUP-Z"
        assert changed.version == 2
        assert count(db, ApprovalRequest) > 0
        assert count(db, AuditEvent) > 0
        assert count(db, IdempotencyRecord) > 0

    reset = client.post("/api/demo/reset", headers=pm_headers)
    assert reset.status_code == 200
    assert reset.json()["purchase_order"]["supplier_id"] == "SUP-Y"
    assert reset.json()["purchase_order"]["version"] == 1

    with SessionLocal() as db:
        restored = db.get(PurchaseOrder, "PO-1007")
        assert restored.supplier_id == "SUP-Y"
        assert restored.version == 1
        assert count(db, ApprovalRequest) == 0
        assert count(db, AttentionItem) == 0
        assert count(db, AgentRun) == 0
        assert count(db, AgentStep) == 0
        assert count(db, AuditEvent) == 0
        assert count(db, IdempotencyRecord) == 0
        assert count(db, Memory) == 6
        assert db.get(Memory, "MEM-PM-SUPPLIER").content == (
            "Supplier Z is approved for emergency Part X coverage.")

    rerun = client.post("/api/proactive/run", headers=pm_headers)
    assert rerun.status_code == 200
    assert rerun.json()[0]["status"] == "OPEN"
    assert client.get("/api/approvals", headers=pm_headers).json()[0]["status"] == "PENDING"


def test_demo_reset_is_disabled_in_production(client, pm_headers, monkeypatch):
    monkeypatch.setattr(settings, "app_environment", "production")
    assert client.post("/api/demo/reset", headers=pm_headers).status_code == 404


def test_demo_reset_requires_explicit_permission(client, floor_headers):
    response = client.post("/api/demo/reset", headers=floor_headers)
    assert response.status_code == 403

