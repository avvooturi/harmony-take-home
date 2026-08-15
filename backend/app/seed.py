from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (CalendarEvent, Email, Employee, EmployeeEmailAccess, ERPActivity,
                     Inventory, KnowledgeDocument, Memory, OrganizationRelationship, Part,
                     ProductionOrder, ProductionOrderPart, PurchaseOrder, Supplier, TeamsMeeting)


PURCHASING_PERMISSIONS = [
    "inventory.read", "purchase_order.read", "production_order.read",
    "supplier.read", "supplier_communication.read", "knowledge.read",
    "purchase_order.propose", "purchase_order.write", "outlook.send",
]


def seed_work_context(db: Session) -> None:
    """Seed source history separately from selective durable agent memory."""
    current_time = datetime.now(timezone.utc)
    emails = [
        Email(id="EMAIL-FLOOR-QUALITY", sender="quality@harmony.local",
              recipients=["frank@harmony.local"], subject="Inspection hold cleared for Order 4812",
              body="Quality cleared the staged components. Final Part X availability remains the floor risk.",
              sent_at=current_time - timedelta(hours=2)),
        Email(id="EMAIL-EXEC-RISK", sender="operations@harmony.local",
              recipients=["avery@harmony.local"], subject="Weekly operations risk digest",
              body="Purchasing has one high-priority material risk; production is tracking Order 4812.",
              sent_at=current_time - timedelta(hours=4)),
    ]
    for email in emails:
        if not db.get(Email, email.id):
            db.add(email)
    db.flush()

    records = [
        EmployeeEmailAccess(employee_id="emp-pm", email_id="EMAIL-DELAY", unread=True, relevance="HIGH"),
        EmployeeEmailAccess(employee_id="emp-floor", email_id="EMAIL-FLOOR-QUALITY", unread=True, relevance="HIGH"),
        EmployeeEmailAccess(employee_id="emp-exec", email_id="EMAIL-EXEC-RISK", unread=True, relevance="HIGH"),
        CalendarEvent(id="CAL-PM-TODAY", employee_id="emp-pm", title="Supplier recovery review",
                      starts_at=current_time.replace(hour=14, minute=0, second=0, microsecond=0),
                      ends_at=current_time.replace(hour=14, minute=30, second=0, microsecond=0)),
        CalendarEvent(id="CAL-FLOOR-TODAY", employee_id="emp-floor", title="Shift material readiness huddle",
                      starts_at=current_time.replace(hour=9, minute=0, second=0, microsecond=0),
                      ends_at=current_time.replace(hour=9, minute=15, second=0, microsecond=0)),
        CalendarEvent(id="CAL-EXEC-TODAY", employee_id="emp-exec", title="Operations portfolio review",
                      starts_at=current_time.replace(hour=11, minute=0, second=0, microsecond=0),
                      ends_at=current_time.replace(hour=12, minute=0, second=0, microsecond=0)),
        TeamsMeeting(id="TEAMS-PM-1", title="Supplier continuity review",
                     participant_ids=["emp-pm", "emp-exec"], occurred_at=current_time - timedelta(days=2),
                     summary="Reviewed repeat delivery variance from Supplier Y.",
                     decisions=["Use Supplier Z for emergency coverage when production is threatened."]),
        TeamsMeeting(id="TEAMS-FLOOR-1", title="Order 4812 shift handoff",
                     participant_ids=["emp-floor"], occurred_at=current_time - timedelta(days=1),
                     summary="Staging is complete except for the remaining Part X requirement.",
                     decisions=["Escalate material availability before the next shift."]),
        OrganizationRelationship(id="ORG-PM-FLOOR", employee_id="emp-pm",
                                 related_employee_id="emp-floor", relationship="production partner"),
        OrganizationRelationship(id="ORG-FLOOR-PM", employee_id="emp-floor",
                                 related_employee_id="emp-pm", relationship="purchasing contact"),
        OrganizationRelationship(id="ORG-EXEC-PM", employee_id="emp-exec",
                                 related_employee_id="emp-pm", relationship="direct report"),
        ERPActivity(id="ERP-PM-RECENT", employee_id="emp-pm", activity_type="PO_REVIEWED",
                    entity_type="purchase_order", entity_id="PO-1007",
                    summary="Reviewed PO-1007 delivery commitment with Supplier Y.",
                    occurred_at=current_time - timedelta(days=1)),
        ERPActivity(id="ERP-FLOOR-RECENT", employee_id="emp-floor", activity_type="WORK_COMPLETED",
                    entity_type="production_order", entity_id="4812",
                    summary="Completed component staging for Production Order 4812.",
                    occurred_at=current_time - timedelta(hours=18)),
        ERPActivity(id="ERP-EXEC-RECENT", employee_id="emp-exec", activity_type="RISK_REVIEWED",
                    entity_type="operations_portfolio", entity_id="WEEKLY",
                    summary="Reviewed the weekly production and purchasing risk portfolio.",
                    occurred_at=current_time - timedelta(days=1)),
    ]
    for record in records:
        identity = ((record.employee_id, record.email_id)
                    if isinstance(record, EmployeeEmailAccess) else record.id)
        if not db.get(type(record), identity):
            db.add(record)

    memories = [
        Memory(id="MEM-PM-ROLE", employee_id="emp-pm", type="responsibility",
               content="Own supplier continuity and purchase-order recovery for production-critical parts.",
               source="organizational_profile", importance=0.95),
        Memory(id="MEM-PM-SUPPLIER", employee_id="emp-pm", type="preferred_supplier",
               content="Supplier Z is approved for emergency Part X coverage.",
               source="approved_decision", importance=0.9),
        Memory(id="MEM-FLOOR-ROLE", employee_id="emp-floor", type="responsibility",
               content="Prepare assigned production orders and escalate material blockers to purchasing.",
               source="organizational_profile", importance=0.95),
        Memory(id="MEM-FLOOR-PREF", employee_id="emp-floor", type="preference",
               content="Prefers concise shift-ready checklists for production handoffs.",
               source="user_preference", importance=0.7),
        Memory(id="MEM-EXEC-ROLE", employee_id="emp-exec", type="responsibility",
               content="Monitor cross-functional operational risk and unblock accountable leaders.",
               source="organizational_profile", importance=0.95),
        Memory(id="MEM-EXEC-PREF", employee_id="emp-exec", type="preference",
               content="Prefers exception-based summaries with owner and business impact.",
               source="user_preference", importance=0.8),
    ]
    for memory in memories:
        if not db.get(Memory, memory.id):
            db.add(memory)
    db.commit()


def seed(db: Session) -> None:
    if db.scalar(select(Employee.id).limit(1)):
        seed_work_context(db)
        return
    today = date.today()
    # Flush referenced rows in explicit phases. Connector models intentionally do not
    # expose ORM relationships, so the seed must not depend on unit-of-work ordering.
    db.add_all([
        Employee(id="emp-pm", name="Maya Chen", role="Purchasing Manager", department="Purchasing", permissions=PURCHASING_PERMISSIONS),
        Employee(id="emp-floor", name="Frank Ortiz", role="Floor Employee", department="Production", permissions=["production_order.read_assigned", "knowledge.read"]),
        Employee(id="emp-exec", name="Avery Brooks", role="Executive", department="Executive", permissions=["inventory.read", "purchase_order.read", "production_order.read", "supplier.read", "knowledge.read", "audit.read"]),
    ])
    db.flush()
    db.add_all([
        Part(id="PART-X", name="Part X"),
        Supplier(id="SUP-Y", name="Supplier Y", lead_time_days=9, approved_parts=["PART-X"]),
        Supplier(id="SUP-Z", name="Supplier Z", lead_time_days=2, approved_parts=["PART-X"]),
    ])
    db.flush()
    db.add_all([
        Inventory(part_id="PART-X", quantity=50, daily_usage=10, projected_stockout=today + timedelta(days=5)),
        PurchaseOrder(id="PO-1007", part_id="PART-X", supplier_id="SUP-Y", quantity=200, expected_date=today + timedelta(days=4), version=1),
        ProductionOrder(id="4812", scheduled_date=today + timedelta(days=7), status="ACTIVE", assigned_employee_id="emp-floor"),
    ])
    db.flush()
    db.add_all([
        ProductionOrderPart(production_order_id="4812", part_id="PART-X", quantity=100),
        Email(id="EMAIL-DELAY", sender="shipping@supplier-y.test", recipients=["maya@harmony.local"], subject="Part X shipment delay", body="The Part X shipment for PO-1007 is delayed and will not arrive until Tuesday.", sent_at=datetime.now(timezone.utc), supplier_id="SUP-Y"),
        CalendarEvent(id="CAL-PRODUCTION", employee_id="emp-pm", title="Production readiness review",
                      starts_at=datetime.now(timezone.utc) + timedelta(days=2),
                      ends_at=datetime.now(timezone.utc) + timedelta(days=2, hours=1)),
        KnowledgeDocument(id="POL-PURCHASE", title="Purchasing Policy", content="Supplier changes require purchasing authority, documented evidence, and explicit approval.", allowed_departments=["Purchasing", "Executive"]),
        KnowledgeDocument(id="POL-EMERGENCY", title="Emergency Supplier Policy", content="An approved alternate supplier may be used when production is at risk. Notify production after the change.", allowed_departments=["Purchasing", "Executive"]),
        KnowledgeDocument(id="PROC-ESCALATION", title="Production Escalation Procedure", content="Notify the production lead promptly when material availability threatens a scheduled order.", allowed_departments=["Purchasing", "Production", "Executive"]),
    ])
    db.commit()
    seed_work_context(db)
