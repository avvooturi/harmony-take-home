from datetime import date, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import CalendarEvent, Email, EmployeeEmailAccess


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

    def todays_calendar(self, employee_id: str) -> list[dict]:
        return [event for event in self.get_calendar_events(employee_id)
                if datetime.fromisoformat(event["starts_at"]).date() == date.today()]

    def relevant_email(self, employee_id: str, unread_only: bool = False) -> list[dict]:
        stmt = (select(Email, EmployeeEmailAccess)
                .join(EmployeeEmailAccess, EmployeeEmailAccess.email_id == Email.id)
                .where(EmployeeEmailAccess.employee_id == employee_id)
                .order_by(Email.sent_at.desc()))
        if unread_only:
            stmt = stmt.where(EmployeeEmailAccess.unread.is_(True))
        return [{**self._dict(email), "sent_at": email.sent_at.isoformat(),
                 "unread": access.unread, "relevance": access.relevance}
                for email, access in self.db.execute(stmt).all()]

    @staticmethod
    def _dict(e: Email) -> dict:
        return {"id": e.id, "sender": e.sender, "recipients": e.recipients,
                "subject": e.subject, "body": e.body, "supplier_id": e.supplier_id,
                "direction": e.direction}
