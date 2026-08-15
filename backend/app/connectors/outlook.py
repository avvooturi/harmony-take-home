from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import CalendarEvent, Email


class OutlookConnector:
    def __init__(self, db: Session):
        self.db = db

    def search_email(self, query: str, supplier_id: str | None = None) -> list[dict]:
        stmt = select(Email).where(or_(Email.subject.ilike(f"%{query}%"), Email.body.ilike(f"%{query}%")))
        if supplier_id:
            stmt = stmt.where(Email.supplier_id == supplier_id)
        return [self._dict(e) for e in self.db.scalars(stmt).all()]

    def send_email(self, sender: str, recipients: list[str], subject: str, body: str) -> dict:
        email = Email(id=f"OUT-{__import__('uuid').uuid4()}", sender=sender, recipients=recipients,
                      subject=subject, body=body, direction="OUTBOUND")
        self.db.add(email)
        self.db.commit()
        return self._dict(email)

    def draft_email(self, sender: str, recipients: list[str], subject: str, body: str) -> dict:
        email = Email(id=f"DRAFT-{__import__('uuid').uuid4()}", sender=sender, recipients=recipients,
                      subject=subject, body=body, direction="DRAFT")
        self.db.add(email)
        self.db.commit()
        return self._dict(email)

    def get_calendar_events(self, employee_id: str) -> list[dict]:
        events = self.db.scalars(select(CalendarEvent).where(CalendarEvent.employee_id == employee_id)).all()
        return [{"id": event.id, "title": event.title, "starts_at": event.starts_at.isoformat(),
                 "ends_at": event.ends_at.isoformat()} for event in events]

    @staticmethod
    def _dict(e: Email) -> dict:
        return {"id": e.id, "sender": e.sender, "recipients": e.recipients,
                "subject": e.subject, "body": e.body, "supplier_id": e.supplier_id,
                "direction": e.direction}
