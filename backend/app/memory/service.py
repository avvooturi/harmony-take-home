from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import Memory


class MemoryService:
    """Durable, selective memory; never a copy of raw enterprise history."""

    def __init__(self, db: Session):
        self.db = db

    def list_for_employee(self, employee_id: str) -> list[dict]:
        current_time = datetime.now(timezone.utc)
        rows = self.db.scalars(select(Memory).where(
            Memory.employee_id == employee_id,
            or_(Memory.expires_at.is_(None), Memory.expires_at > current_time),
        ).order_by(Memory.importance.desc(), Memory.updated_at.desc())).all()
        return [{"id": row.id, "type": row.type, "content": row.content,
                 "source": row.source, "importance": row.importance,
                 "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(),
                 "expires_at": row.expires_at.isoformat() if row.expires_at else None}
                for row in rows]

    def remember(self, employee_id: str, memory_type: str, content: str, source: str,
                 importance: float = 0.5, expires_at: datetime | None = None) -> Memory:
        memory = Memory(employee_id=employee_id, type=memory_type, content=content,
                        source=source, importance=importance, expires_at=expires_at)
        self.db.add(memory)
        self.db.commit()
        return memory

