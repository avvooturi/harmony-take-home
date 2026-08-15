from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (CalendarEvent, Email, Employee, Inventory, KnowledgeDocument, Part, ProductionOrder,
                     ProductionOrderPart, PurchaseOrder, Supplier)


PURCHASING_PERMISSIONS = [
    "inventory.read", "purchase_order.read", "production_order.read",
    "supplier.read", "supplier_communication.read", "knowledge.read",
    "purchase_order.propose", "purchase_order.write", "outlook.send",
]


def seed(db: Session) -> None:
    if db.scalar(select(Employee.id).limit(1)):
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
