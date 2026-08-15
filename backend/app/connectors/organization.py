from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Employee, OrganizationRelationship


class OrganizationConnector:
    def __init__(self, db: Session):
        self.db = db

    def relationships(self, employee_id: str) -> list[dict]:
        rows = self.db.scalars(select(OrganizationRelationship).where(
            OrganizationRelationship.employee_id == employee_id)).all()
        return [{"employee_id": row.related_employee_id,
                 "name": self.db.get(Employee, row.related_employee_id).name,
                 "relationship": row.relationship} for row in rows]

