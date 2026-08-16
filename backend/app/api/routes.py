from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agent.context import ContextService
from ..agent.provider import DeterministicProvider
from ..auth.service import AuthorizationService
from ..connectors.erp import ERPConnector, VersionConflict
from ..connectors.outlook import OutlookConnector
from ..db import get_db
from ..models import (AgentRun, AgentStep, ApprovalRequest, AttentionItem, AuditEvent,
                      Employee)
from ..proactive.service import ProactiveService
from ..tools.registry import ToolRegistry
from .dependencies import get_current_employee
from .schemas import ChatRequest, Decision, ToolRequest, serialize

router = APIRouter(prefix="/api")


def send_production_notification(db: Session, run_id: str) -> dict:
    """Bounded retry for the independently recoverable notification step."""
    last_error = "unknown failure"
    for attempt in range(1, 4):
        try:
            notification = OutlookConnector(db).send_email(
                "agent@harmony.local", ["production@harmony.local"],
                "Supplier changed for PO-1007",
                "PO-1007 was moved to Supplier Z to protect Production Order 4812.",
            )
            db.add(AgentStep(run_id=run_id, name="NOTIFY_PRODUCTION", status="COMPLETED",
                             attempts=attempt, result=notification))
            return notification
        except Exception as exc:  # connector implementations classify transient errors in production
            db.rollback()
            last_error = str(exc)
    db.add(AgentStep(run_id=run_id, name="NOTIFY_PRODUCTION", status="FAILED",
                     attempts=3, result={"error": last_error}))
    db.commit()
    raise HTTPException(503, "PO changed, but production notification failed; retry this step")


@router.get("/health")
def health(): return {"status": "ok"}


@router.get("/employees")
def employees(db: Session = Depends(get_db)):
    return [serialize(e, ["id", "name", "role", "department", "permissions"])
            for e in db.scalars(select(Employee)).all()]


@router.get("/me")
def me(employee: Employee = Depends(get_current_employee)):
    return serialize(employee, ["id", "name", "role", "department", "permissions"])


@router.get("/work-context")
def work_context(employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    return ContextService(db).work_context(employee)


@router.get("/work-context/{employee_id}")
def employee_work_context(employee_id: str, employee: Employee = Depends(get_current_employee),
                          db: Session = Depends(get_db)):
    subject = db.get(Employee, employee_id)
    if not subject:
        raise HTTPException(404, "Employee not found")
    return ContextService(db).work_context(employee, subject)


@router.post("/proactive/run")
def proactive(employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    AuthorizationService.require(employee, "purchase_order.propose")
    return [serialize(i, ["id", "run_id", "priority", "title", "evidence", "recommendation", "status"])
            for i in ProactiveService(db).run(employee)]


@router.get("/attention")
def attention(employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    rows = db.scalars(select(AttentionItem).where(
        AttentionItem.employee_id == employee.id,
        AttentionItem.status != "DISMISSED",
    )).all()
    return [serialize(i, ["id", "run_id", "priority", "title", "evidence", "recommendation", "status"])
            for i in rows]


@router.get("/approvals")
def approvals(employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    rows = db.scalars(select(ApprovalRequest).where(ApprovalRequest.requested_by == employee.id)).all()
    return [serialize(a, ["id", "run_id", "tool_name", "arguments", "reason", "evidence", "status", "decided_at"])
            for a in rows]


@router.post("/approvals/{approval_id}/decision")
def decide(approval_id: str, body: Decision, employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    approval = db.get(ApprovalRequest, approval_id)
    if not approval or approval.requested_by != employee.id:
        raise HTTPException(404, "Approval not found")
    if approval.status != "PENDING":
        return {"status": approval.status, "message": "Decision already recorded"}
    if body.decision.upper() == "REJECT":
        approval.status, approval.decided_at = "REJECTED", datetime.now(timezone.utc)
        item = db.scalar(select(AttentionItem).where(AttentionItem.run_id == approval.run_id))
        if item:
            item.status = "REJECTED"
        db.add(AuditEvent(run_id=approval.run_id, employee_id=employee.id, event_type="ACTION_REJECTED", details={"approval_id": approval.id}))
        db.commit()
        return {"status": "REJECTED"}
    if body.decision.upper() != "APPROVE":
        raise HTTPException(422, "Decision must be APPROVE or REJECT")
    # Reauthorize at execution time. Approval is evidence of intent, not authority.
    try:
        result = ToolRegistry(db).invoke(employee, approval.tool_name, approval.arguments, approved=True, run_id=approval.run_id)
    except VersionConflict as exc:
        approval.status = "STALE"
        db.add(AuditEvent(run_id=approval.run_id, employee_id=employee.id, event_type="VERSION_CONFLICT", details={"error": str(exc)}))
        db.commit()
        raise HTTPException(409, str(exc)) from exc
    db.add(AgentStep(run_id=approval.run_id, name="EXECUTE_PO_CHANGE", status="COMPLETED", attempts=1, result=result))
    db.commit()  # durable boundary: a notification retry must never repeat the PO mutation
    notification = send_production_notification(db, approval.run_id)
    approval.status, approval.decided_at = "APPROVED", datetime.now(timezone.utc)
    verified = ERPConnector(db).purchase_order(approval.arguments["po_id"])
    run = db.get(AgentRun, approval.run_id)
    run.state = "AUDIT"
    item = db.scalar(select(AttentionItem).where(AttentionItem.run_id == approval.run_id))
    if item:
        item.status = "RESOLVED"
    db.add(AuditEvent(run_id=approval.run_id, employee_id=employee.id, event_type="ACTION_EXECUTED",
                      details={"result": result, "verified": verified, "notification_id": notification["id"]}))
    db.commit()
    return {"status": "APPROVED", "result": result, "verified": verified, "notification": notification}


@router.post("/attention/{attention_id}/dismiss")
def dismiss_attention(attention_id: str, employee: Employee = Depends(get_current_employee),
                      db: Session = Depends(get_db)):
    item = db.get(AttentionItem, attention_id)
    if not item or item.employee_id != employee.id or item.status == "DISMISSED":
        raise HTTPException(404, "Attention item not found")
    approval = db.scalar(select(ApprovalRequest).where(ApprovalRequest.run_id == item.run_id))
    if not approval or approval.status == "PENDING":
        raise HTTPException(409, "Decide the approval before dismissing this task")
    previous_status = item.status
    item.status = "DISMISSED"
    db.add(AuditEvent(run_id=item.run_id, employee_id=employee.id,
                      event_type="ATTENTION_DISMISSED",
                      details={"attention_id": item.id, "decision": approval.status,
                               "previous_status": previous_status}))
    db.commit()
    return {"status": "DISMISSED", "attention_id": item.id,
            "decision": approval.status}


@router.get("/audit")
def audit(employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    # Employees see their own audit; executives with audit.read see all.
    stmt = select(AuditEvent).order_by(AuditEvent.created_at.desc())
    if "audit.read" not in employee.permissions:
        stmt = stmt.where(AuditEvent.employee_id == employee.id)
    return [serialize(a, ["id", "run_id", "employee_id", "event_type", "details", "created_at"])
            for a in db.scalars(stmt).all()]


@router.get("/erp/purchase-orders/{po_id}")
def purchase_order(po_id: str, employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    AuthorizationService.require(employee, "purchase_order.read")
    return ERPConnector(db).purchase_order(po_id)


@router.get("/erp/production-orders/{order_id}")
def production_order(order_id: str, employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    order = ERPConnector(db).production_order(order_id)
    if "production_order.read" in employee.permissions:
        return order
    AuthorizationService.require(employee, "production_order.read_assigned")
    if order["assigned_employee_id"] != employee.id:
        raise HTTPException(403, "Production order is not assigned to this employee")
    return order


@router.post("/tools/invoke")
def invoke_tool(body: ToolRequest, employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)):
    return ToolRegistry(db).invoke(employee, body.name, body.arguments)


@router.post("/agent/chat")
def chat(body: ChatRequest, employee: Employee = Depends(get_current_employee)):
    return {"message": DeterministicProvider().generate(body.message), "employee": employee.name,
            "note": "Chat can recommend; actions only run through registered tools and approval."}
