from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import Employee, KnowledgeDocument


class KnowledgeConnector:
    def __init__(self, db: Session):
        self.db = db

    def search(self, query: str, employee: Employee) -> list[dict]:
        words = [word for word in query.split() if len(word) > 3]
        stmt = select(KnowledgeDocument)
        if words:
            stmt = stmt.where(or_(*[KnowledgeDocument.content.ilike(f"%{w}%") for w in words]))
        docs = self.db.scalars(stmt).all()
        return [{"id": d.id, "title": d.title, "content": d.content} for d in docs
                if employee.department in d.allowed_departments]

