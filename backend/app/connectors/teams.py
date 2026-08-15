from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import TeamsMeeting


class TeamsConnector:
    """Mock Teams adapter; raw meeting history remains source-owned."""

    def __init__(self, db: Session):
        self.db = db

    def recent_meetings(self, employee_id: str) -> list[dict]:
        meetings = self.db.scalars(select(TeamsMeeting).order_by(TeamsMeeting.occurred_at.desc())).all()
        return [{"id": m.id, "title": m.title, "occurred_at": m.occurred_at.isoformat(),
                 "summary": m.summary, "decisions": m.decisions}
                for m in meetings if employee_id in m.participant_ids]

