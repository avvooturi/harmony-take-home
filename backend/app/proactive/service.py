from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agent.orchestrator import Orchestrator
from ..connectors.erp import ERPConnector
from ..models import AttentionItem, Employee


class ProactiveService:
    def __init__(self, db: Session):
        self.db = db

    def run(self, employee: Employee) -> list[AttentionItem]:
        existing = self.db.scalars(select(AttentionItem).where(
            AttentionItem.employee_id == employee.id, AttentionItem.status == "OPEN")).all()
        if existing:
            return list(existing)
        return [Orchestrator(self.db).analyze_shortage(employee, c)
                for c in ERPConnector(self.db).shortage_candidates()]

