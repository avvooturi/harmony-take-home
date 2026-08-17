from sqlalchemy import select

from app.agent.chat import AgentChatService
from app.agent import provider as provider_module
from app.agent.provider import LLMProvider, OllamaProvider
from app.connectors.erp import ERPConnector
from app.db import SessionLocal
from app.models import AuditEvent, Employee, PurchaseOrder


class RecordingProvider(LLMProvider):
    name = "test-local"

    def __init__(self):
        self.prompts = []

    @property
    def model(self):
        return "test-model"

    def generate(self, prompt, system_prompt=None):
        self.prompts.append((prompt, system_prompt))
        question = prompt.split("USER QUESTION:\n", 1)[1].split("\n\nAUTHORIZED CONTEXT:", 1)[0]
        return f"Relevant answer for: {question}"


class FailingProvider(LLMProvider):
    name = "broken-local"

    @property
    def model(self):
        return "broken-model"

    def generate(self, prompt, system_prompt=None):
        raise TimeoutError("local model unavailable")


def test_local_provider_receives_actual_user_question():
    with SessionLocal() as db:
        provider = RecordingProvider()
        employee = db.get(Employee, "emp-pm")
        AgentChatService(db, local_provider=provider).respond(employee, "Why is Part X at risk?")
        assert "Why is Part X at risk?" in provider.prompts[0][0]
        assert "enterprise work assistant" in provider.prompts[0][1]


def test_different_questions_produce_different_responses():
    with SessionLocal() as db:
        provider = RecordingProvider()
        employee = db.get(Employee, "emp-pm")
        service = AgentChatService(db, local_provider=provider)
        first = service.respond(employee, "Why is Part X at risk?")
        second = service.respond(employee, "What should I focus on today?")
        assert first.message != second.message


def test_unrelated_input_does_not_force_part_x_recommendation():
    with SessionLocal() as db:
        employee = db.get(Employee, "emp-pm")
        result = AgentChatService(db, local_provider=FailingProvider()).respond(
            employee, "test tesr 125")
        assert "clarify" in result.message.lower()
        assert "Part X will likely cause" not in result.message


def test_employee_context_is_scoped_to_active_employee():
    with SessionLocal() as db:
        provider = RecordingProvider()
        floor = db.get(Employee, "emp-floor")
        AgentChatService(db, local_provider=provider).respond(floor, "What should I focus on today?")
        prompt = provider.prompts[0][0]
        assert "Frank Ortiz" in prompt
        assert "Assigned Production Order 4812" in prompt
        assert "Supplier Y recently reported" not in prompt


def test_unauthorized_purchasing_context_is_not_passed_to_floor_model():
    with SessionLocal() as db:
        provider = RecordingProvider()
        floor = db.get(Employee, "emp-floor")
        AgentChatService(db, local_provider=provider).respond(floor, "Explain supplier and inventory risk")
        prompt = provider.prompts[0][0]
        assert "PO-1007" not in prompt
        assert "shipping@supplier-y.test" not in prompt
        assert "purchase_order.write" not in prompt


def test_model_failure_triggers_audited_deterministic_fallback():
    with SessionLocal() as db:
        employee = db.get(Employee, "emp-pm")
        result = AgentChatService(db, local_provider=FailingProvider()).respond(
            employee, "What should I focus on today?")
        assert result.reasoning_mode == "deterministic_fallback"
        assert result.fallback_error.startswith("TimeoutError")
        event = db.scalar(select(AuditEvent).where(AuditEvent.event_type == "AGENT_INTERACTION"))
        assert event.details["reasoning_mode"] == "deterministic_fallback"
        assert event.details["user_message"] == "What should I focus on today?"


def test_model_output_cannot_directly_mutate_erp():
    class ClaimsMutation(RecordingProvider):
        def generate(self, prompt, system_prompt=None):
            return "I changed PO-1007 to Supplier Z."

    with SessionLocal() as db:
        employee = db.get(Employee, "emp-pm")
        AgentChatService(db, local_provider=ClaimsMutation()).respond(employee, "Change the supplier")
        assert db.get(PurchaseOrder, "PO-1007").supplier_id == "SUP-Y"
        assert db.get(PurchaseOrder, "PO-1007").version == 1


def test_chat_proposal_does_not_bypass_write_approval(client, pm_headers):
    response = client.post("/api/tools/invoke", headers=pm_headers, json={
        "name": "change_purchase_order_supplier",
        "arguments": {"po_id": "PO-1007", "supplier_id": "SUP-Z",
                      "expected_version": 1, "key": "chat-cannot-approve"},
    })
    assert response.status_code == 409


def test_proactive_shortage_detection_remains_deterministic():
    with SessionLocal() as db:
        candidates = ERPConnector(db).shortage_candidates()
        assert candidates == [{"part_id": "PART-X", "production_order_id": "4812",
                               "po_id": "PO-1007"}]


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_available_configured_ollama_model_uses_local_provider(monkeypatch):
    OllamaProvider.clear_availability_cache()
    monkeypatch.setattr(provider_module.httpx, "get", lambda *args, **kwargs: FakeResponse({
        "models": [{"name": provider_module.settings.ollama_model}],
    }))
    monkeypatch.setattr(provider_module.httpx, "post", lambda *args, **kwargs: FakeResponse({
        "response": "Local model used the supplied question and context.",
    }))
    with SessionLocal() as db:
        employee = db.get(Employee, "emp-pm")
        result = AgentChatService(db).respond(employee, "What should I prioritize?")
        assert result.reasoning_mode == "local_ai"
        assert result.provider == "ollama"
        assert result.model == provider_module.settings.ollama_model


def test_unavailable_ollama_is_health_checked_once_then_fast_cached(monkeypatch):
    OllamaProvider.clear_availability_cache()
    calls = {"health": 0, "generate": 0}

    def unavailable(*args, **kwargs):
        calls["health"] += 1
        raise ConnectionError("not running")

    def should_not_generate(*args, **kwargs):
        calls["generate"] += 1
        raise AssertionError("generation should be skipped when health check fails")

    monkeypatch.setattr(provider_module.httpx, "get", unavailable)
    monkeypatch.setattr(provider_module.httpx, "post", should_not_generate)
    with SessionLocal() as db:
        employee = db.get(Employee, "emp-pm")
        first = AgentChatService(db).respond(employee, "What are my current tasks?")
        second = AgentChatService(db).respond(employee, "What should I prioritize?")
        assert first.reasoning_mode == second.reasoning_mode == "deterministic_fallback"
        assert calls == {"health": 1, "generate": 0}


def test_approval_language_routes_to_pending_approval_without_mutation(client, pm_headers):
    client.post("/api/proactive/run", headers=pm_headers)
    for phrase in ("approve", "proceed", "do it"):
        response = client.post("/api/agent/chat", headers=pm_headers,
                               json={"message": phrase})
        assert response.status_code == 200
        payload = response.json()
        assert payload["proposed_action"]["type"] == "review_pending_approval"
        assert "can’t authorize or execute" in payload["message"]
    with SessionLocal() as db:
        assert db.get(PurchaseOrder, "PO-1007").supplier_id == "SUP-Y"
        assert db.get(PurchaseOrder, "PO-1007").version == 1


def test_deterministic_fallback_answers_tasks_and_priorities():
    with SessionLocal() as db:
        employee = db.get(Employee, "emp-pm")
        service = AgentChatService(db, local_provider=FailingProvider())
        tasks = service.respond(employee, "What are my current tasks?").message
        priorities = service.respond(employee, "What should I prioritize?").message
        assert "current authorized tasks" in tasks
        assert "focus on" in priorities
        assert "Part X inventory risk" in priorities
