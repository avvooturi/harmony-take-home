from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.service import AuthorizationService
from ..connectors.erp import ERPConnector
from ..connectors.knowledge import KnowledgeConnector
from ..connectors.organization import OrganizationConnector
from ..connectors.outlook import OutlookConnector
from ..connectors.teams import TeamsConnector
from ..memory.service import MemoryService
from ..models import AgentRun, ApprovalRequest, Employee, Memory


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

    def work_context(self, requester: Employee, subject: Employee | None = None) -> dict:
        """Build an authorized, per-user view without copying source-system history."""
        subject = subject or requester
        if requester.id != subject.id and "work_context.read_all" not in requester.permissions:
            raise HTTPException(403, "Cannot retrieve another employee's work context")

        outlook = OutlookConnector(self.db)
        current_work = []
        recent = []
        recommendations = []

        for event in outlook.todays_calendar(subject.id):
            current_work.append({"source": "Outlook Calendar", "title": event["title"],
                                 "detail": f"Today at {event['starts_at']}", "status": "SCHEDULED"})
        emails = outlook.relevant_email(subject.id)
        for email in [item for item in emails if item["unread"]]:
            current_work.append({"source": "Outlook", "title": email["subject"],
                                 "detail": email["body"], "status": "UNREAD"})
        for email in emails:
            recent.append({"source": "Outlook", "title": email["subject"],
                           "detail": email["body"], "occurred_at": email["sent_at"]})

        for meeting in TeamsConnector(self.db).recent_meetings(subject.id):
            recent.append({"source": "Teams", "title": meeting["title"],
                           "detail": meeting["summary"], "occurred_at": meeting["occurred_at"],
                           "decisions": meeting["decisions"]})
        for activity in self.erp.recent_activity(subject.id):
            recent.append({"source": "ERP", "title": activity["type"],
                           "detail": activity["summary"], "occurred_at": activity["occurred_at"]})
        runs = self.db.scalars(select(AgentRun).where(
            AgentRun.employee_id == subject.id).order_by(AgentRun.created_at.desc()).limit(3)).all()
        for run in runs:
            if run.recommendation:
                recent.append({"source": "Agent", "title": "Previous recommendation",
                               "detail": run.recommendation, "occurred_at": run.created_at.isoformat()})

        memories = MemoryService(self.db).list_for_employee(subject.id)
        memory_text = " ".join(item["content"] for item in memories)
        if subject.role == "Purchasing Manager":
            for permission in ("inventory.read", "purchase_order.read", "production_order.read"):
                AuthorizationService.require(subject, permission)
            inventory = self.erp.inventory("PART-X")
            po = self.erp.purchase_order("PO-1007")
            current_work.extend([
                {"source": "ERP", "title": "Part X inventory risk",
                 "detail": f"Projected stockout: {inventory['projected_stockout']}; {inventory['quantity']} on hand.",
                 "status": "AT_RISK"},
                {"source": "ERP", "title": "Open PO-1007",
                 "detail": f"{po['quantity']} units from {po['supplier_name']}; version {po['version']}.",
                 "status": po["status"]},
            ])
            approvals = self.db.scalars(select(ApprovalRequest).where(
                ApprovalRequest.requested_by == subject.id,
                ApprovalRequest.status == "PENDING")).all()
            for approval in approvals:
                current_work.append({"source": "Agent", "title": "Open supplier-change approval",
                                     "detail": approval.reason, "status": "PENDING"})
            delay = next((mail for mail in emails if "delay" in (mail["subject"] + mail["body"]).lower()), None)
            supplier_memory = "Supplier Z" in memory_text
            recommendations.append({
                "title": "Prepare Part X supplier recovery",
                "detail": ("Part X is projected to run out in five days. "
                           + ("Supplier Y recently reported another delay. " if delay else "")
                           + ("Supplier Z is already approved for emergency coverage. " if supplier_memory else "")
                           + "I can prepare a supplier change and notify production."),
                "action": "RUN_PROACTIVE_ANALYSIS", "permission": "purchase_order.propose",
                "available": "purchase_order.propose" in subject.permissions,
            })
        elif subject.role == "Floor Employee":
            AuthorizationService.require(subject, "production_order.read_assigned")
            for order in self.erp.assigned_orders(subject.id):
                current_work.append({"source": "ERP", "title": f"Assigned Production Order {order['id']}",
                                     "detail": f"Scheduled {order['scheduled_date']}; material staging required.",
                                     "status": order["status"]})
            recommendations.append({
                "title": "Escalate the Part X material blocker",
                "detail": "Order 4812 staging is otherwise complete. Confirm remaining Part X at the shift huddle and escalate availability to your purchasing contact; you cannot change the PO.",
                "action": "CONTACT_PURCHASING", "permission": "production_order.read_assigned",
                "available": True,
            })
        else:
            AuthorizationService.require(subject, "inventory.read")
            inventory = self.erp.inventory("PART-X")
            current_work.append({"source": "ERP", "title": "Cross-functional material risk",
                                 "detail": f"Part X projects to stock out on {inventory['projected_stockout']}.",
                                 "status": "AT_RISK"})
            recommendations.append({
                "title": "Confirm accountable owner and business impact",
                "detail": "Review the purchasing risk with Maya Chen and confirm whether Order 4812 requires executive escalation. No purchasing mutation is available to this role.",
                "action": "REVIEW_RISK", "permission": "inventory.read", "available": True,
            })

        return {
            "employee": {"id": subject.id, "name": subject.name, "role": subject.role,
                         "department": subject.department, "permissions": subject.permissions,
                         "relationships": OrganizationConnector(self.db).relationships(subject.id)},
            "current_work": current_work,
            "recent_context": recent,
            "long_term_memory": memories,
            "recommended_actions": recommendations,
            "provenance": {"current_and_recent": "Retrieved on demand from source connectors",
                           "long_term_memory": "Selective records persisted by MemoryService"},
        }
