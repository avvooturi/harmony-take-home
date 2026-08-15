from datetime import date

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models import (ERPActivity, IdempotencyRecord, Inventory, Part, ProductionOrder,
                      ProductionOrderPart, PurchaseOrder, Supplier)


class VersionConflict(Exception):
    pass


class ERPConnector:
    """Only supported boundary between agent modules and mock ERP tables."""

    def __init__(self, db: Session):
        self.db = db

    def inventory(self, part_id: str) -> dict:
        row, part = self.db.get(Inventory, part_id), self.db.get(Part, part_id)
        if not row or not part:
            raise HTTPException(404, "Part inventory not found")
        return {"part_id": part_id, "part_name": part.name, "quantity": row.quantity,
                "daily_usage": row.daily_usage, "projected_stockout": row.projected_stockout.isoformat()}

    def purchase_order(self, po_id: str) -> dict:
        po = self.db.get(PurchaseOrder, po_id)
        if not po:
            raise HTTPException(404, "Purchase order not found")
        supplier = self.db.get(Supplier, po.supplier_id)
        return {"id": po.id, "part_id": po.part_id, "supplier_id": po.supplier_id,
                "supplier_name": supplier.name, "quantity": po.quantity,
                "expected_date": po.expected_date.isoformat(), "status": po.status, "version": po.version}

    def production_order(self, order_id: str) -> dict:
        order = self.db.get(ProductionOrder, order_id)
        if not order:
            raise HTTPException(404, "Production order not found")
        parts = self.db.scalars(select(ProductionOrderPart).where(ProductionOrderPart.production_order_id == order_id)).all()
        return {"id": order.id, "scheduled_date": order.scheduled_date.isoformat(), "status": order.status,
                "assigned_employee_id": order.assigned_employee_id,
                "parts": [{"part_id": p.part_id, "quantity": p.quantity} for p in parts]}

    def alternatives(self, part_id: str, exclude: str | None = None) -> list[dict]:
        suppliers = self.db.scalars(select(Supplier)).all()
        return [{"id": s.id, "name": s.name, "lead_time_days": s.lead_time_days}
                for s in suppliers if part_id in s.approved_parts and s.id != exclude]

    def shortage_candidates(self, threshold_days: int = 7) -> list[dict]:
        today = date.today()
        inventories = self.db.scalars(select(Inventory)).all()
        result = []
        for inv in inventories:
            if (inv.projected_stockout - today).days > threshold_days:
                continue
            links = self.db.scalars(select(ProductionOrderPart).where(ProductionOrderPart.part_id == inv.part_id)).all()
            for link in links:
                order = self.db.get(ProductionOrder, link.production_order_id)
                if order and order.status == "ACTIVE":
                    po = self.db.scalar(select(PurchaseOrder).where(PurchaseOrder.part_id == inv.part_id, PurchaseOrder.status == "OPEN"))
                    if po:
                        result.append({"part_id": inv.part_id, "production_order_id": order.id, "po_id": po.id})
        return result

    def change_supplier(self, po_id: str, supplier_id: str, expected_version: int, key: str) -> dict:
        prior = self.db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.key == key))
        if prior and prior.completed:
            return {**prior.result, "idempotent_replay": True}
        result = self.db.execute(update(PurchaseOrder).where(
            PurchaseOrder.id == po_id, PurchaseOrder.version == expected_version
        ).values(supplier_id=supplier_id, version=expected_version + 1))
        if result.rowcount != 1:
            self.db.rollback()
            raise VersionConflict("Purchase order changed; reevaluation is required")
        payload = {"po_id": po_id, "supplier_id": supplier_id, "version": expected_version + 1}
        self.db.add(IdempotencyRecord(key=key, operation="change_supplier", result=payload, completed=True))
        self.db.commit()
        return {**payload, "idempotent_replay": False}

    def assigned_orders(self, employee_id: str) -> list[dict]:
        orders = self.db.scalars(select(ProductionOrder).where(
            ProductionOrder.assigned_employee_id == employee_id,
            ProductionOrder.status == "ACTIVE")).all()
        return [self.production_order(order.id) for order in orders]

    def recent_activity(self, employee_id: str) -> list[dict]:
        rows = self.db.scalars(select(ERPActivity).where(
            ERPActivity.employee_id == employee_id).order_by(ERPActivity.occurred_at.desc())).all()
        return [{"id": row.id, "type": row.activity_type, "entity_type": row.entity_type,
                 "entity_id": row.entity_id, "summary": row.summary,
                 "occurred_at": row.occurred_at.isoformat()} for row in rows]
