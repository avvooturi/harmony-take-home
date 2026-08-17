import json
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import AuditEvent, Employee
from .context import ContextService
from .provider import DeterministicProvider, LLMProvider, OllamaProvider


SYSTEM_PROMPT = """You are the current employee's enterprise work assistant.
Use only the authorized context supplied by the application. Do not claim access to other information.
Do not fabricate ERP, email, calendar, Teams, or company facts.
Clearly distinguish facts from recommendations and explain recommendations with supplied evidence.
Never claim an enterprise mutation happened unless the context confirms it.
You may suggest an action, but you cannot authorize or execute it. Application controls and human approval decide that.
If the request is unclear, ask for clarification instead of forcing a purchasing scenario.
Respond concisely and do not reveal hidden chain-of-thought."""


@dataclass
class ChatResult:
    message: str
    reasoning_mode: str
    provider: str
    model: str
    context_sources: list[str]
    proposed_action: dict | None
    fallback_error: str | None = None


class AgentChatService:
    def __init__(self, db: Session, local_provider: LLMProvider | None = None,
                 fallback_provider: LLMProvider | None = None):
        self.db = db
        self.local = local_provider or OllamaProvider()
        self.fallback = fallback_provider or DeterministicProvider()

    def respond(self, employee: Employee, question: str) -> ChatResult:
        context = ContextService(self.db).chat_context(employee, question)
        prompt = self._prompt(question, context)
        fallback_error = None
        try:
            message = self.local.generate(prompt, SYSTEM_PROMPT)
            provider, mode = self.local, "local_ai"
        except Exception as exc:
            fallback_error = f"{type(exc).__name__}: {exc}"
            message = self.fallback.generate(prompt, SYSTEM_PROMPT)
            provider, mode = self.fallback, "deterministic_fallback"
        sources = self._sources(context)
        proposed_action = self._proposed_action(employee, question, message)
        result = ChatResult(message=message, reasoning_mode=mode, provider=provider.name,
                            model=provider.model, context_sources=sources,
                            proposed_action=proposed_action, fallback_error=fallback_error)
        self.db.add(AuditEvent(employee_id=employee.id, event_type="AGENT_INTERACTION", details={
            "user_message": question, "provider": result.provider, "model": result.model,
            "reasoning_mode": result.reasoning_mode, "context_sources": sources,
            "response": message, "proposed_action": proposed_action,
            "fallback_error": fallback_error,
        }))
        self.db.commit()
        return result

    @staticmethod
    def _prompt(question: str, context: dict) -> str:
        return f"USER QUESTION:\n{question}\n\nAUTHORIZED CONTEXT:\n{json.dumps(context, default=str)}"

    @staticmethod
    def _sources(context: dict) -> list[str]:
        sources = {item["source"] for key in ("current_work", "recent_context")
                   for item in context.get(key, [])}
        if context.get("long_term_memory"):
            sources.add("Long-term memory")
        sources.add("Employee profile")
        return sorted(sources)

    @staticmethod
    def _proposed_action(employee: Employee, question: str, response: str) -> dict | None:
        combined = f"{question} {response}".lower()
        if "supplier" in combined and any(term in combined for term in ("change", "move", "prepare")):
            return {"type": "change_purchase_order_supplier", "status": "PROPOSED_ONLY",
                    "authorized_to_propose": "purchase_order.propose" in employee.permissions,
                    "requires_human_approval": True,
                    "next_step": "Run controlled proactive analysis to create an approval request"}
        return None
