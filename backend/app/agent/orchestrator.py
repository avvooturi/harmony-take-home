from sqlalchemy.orm import Session

from ..models import AgentRun, AgentStep, ApprovalRequest, AttentionItem, AuditEvent, Employee
from .context import ContextService
from .provider import DeterministicProvider, LLMProvider


class Orchestrator:
    STATES = ["UNDERSTAND", "RETRIEVE_CONTEXT", "REASON", "PLAN", "RECOMMEND",
              "REQUEST_TOOL", "AUTHORIZE", "REQUEST_APPROVAL"]

    def __init__(self, db: Session, provider: LLMProvider | None = None):
        self.db = db
        self.provider = provider or DeterministicProvider()

    def analyze_shortage(self, employee: Employee, candidate: dict) -> AttentionItem:
        run = AgentRun(employee_id=employee.id, trigger="PROACTIVE_SHORTAGE", state="UNDERSTAND",
                       plan={"candidate": candidate, "steps": self.STATES})
        self.db.add(run)
        self.db.flush()
        for state in self.STATES[:2]:
            self.db.add(AgentStep(run_id=run.id, name=state, status="COMPLETED", attempts=1))
        context = ContextService(self.db).purchasing_risk(employee, candidate)
        recommendation = self.provider.generate(str(context))
        evidence = [
            f"{context['inventory']['part_name']} reaches zero on {context['inventory']['projected_stockout']}",
            context["supplier_emails"][0]["body"] if context["supplier_emails"] else "No supplier delay email found",
            f"Production Order {context['production_order']['id']} requires {candidate['part_id']}",
            f"Supplier Z lead time is {context['alternatives'][0]['lead_time_days']} days",
        ]
        po, alternative = context["purchase_order"], context["alternatives"][0]
        approval = ApprovalRequest(run_id=run.id, requested_by=employee.id,
            tool_name="change_purchase_order_supplier",
            arguments={"po_id": po["id"], "supplier_id": alternative["id"],
                       "expected_version": po["version"], "key": f"{run.id}:supplier-change"},
            reason=recommendation, evidence=evidence)
        item = AttentionItem(run_id=run.id, employee_id=employee.id, priority="HIGH",
            title="Part X shortage threatens Production Order 4812", evidence=evidence,
            recommendation="Move PO-1007 from Supplier Y to Supplier Z")
        run.state, run.recommendation = "REQUEST_APPROVAL", recommendation
        self.db.add_all([approval, item, AuditEvent(run_id=run.id, employee_id=employee.id,
            event_type="RECOMMENDATION_CREATED", details={"sources": ["ERP", "Outlook", "Knowledge"],
            "recommendation": recommendation, "evidence": evidence, "model": run.model_info})])
        self.db.commit()
        return item

