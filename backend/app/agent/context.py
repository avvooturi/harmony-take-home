from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.service import AuthorizationService
from ..connectors.erp import ERPConnector
from ..connectors.knowledge import KnowledgeConnector
from ..connectors.outlook import OutlookConnector
from ..models import Employee, Memory


class ContextService:
    def __init__(self, db: Session):
        self.db, self.erp = db, ERPConnector(db)

    def purchasing_risk(self, employee: Employee, candidate: dict) -> dict:
        auth = AuthorizationService()
        for permission in ("inventory.read", "purchase_order.read", "production_order.read",
                           "supplier.read", "supplier_communication.read", "knowledge.read"):
            auth.require(employee, permission)
        po = self.erp.purchase_order(candidate["po_id"])
        context = {
            "employee": {"id": employee.id, "role": employee.role, "permissions": employee.permissions},
            "inventory": self.erp.inventory(candidate["part_id"]),
            "purchase_order": po,
            "production_order": self.erp.production_order(candidate["production_order_id"]),
            "supplier_emails": OutlookConnector(self.db).search_email("delay", po["supplier_id"]),
            "alternatives": self.erp.alternatives(candidate["part_id"], po["supplier_id"]),
            "knowledge": KnowledgeConnector(self.db).search("supplier production approval escalation", employee),
            "memories": [m.content for m in self.db.scalars(select(Memory).where(Memory.employee_id == employee.id)).all()],
        }
        return context

