from sqlalchemy import func, select

from app.agent.context import ContextService
from app.db import SessionLocal
from app.memory.service import MemoryService
from app.models import Email, Employee, Memory, TeamsMeeting


def context(client, employee_id):
    response = client.get("/api/work-context", headers={"X-Employee-Id": employee_id})
    assert response.status_code == 200
    return response.json()


def test_different_employees_receive_different_work_context(client):
    purchasing = context(client, "emp-pm")
    floor = context(client, "emp-floor")
    purchasing_titles = {item["title"] for item in purchasing["current_work"]}
    floor_titles = {item["title"] for item in floor["current_work"]}
    assert "Part X inventory risk" in purchasing_titles
    assert "Assigned Production Order 4812" in floor_titles
    assert purchasing_titles != floor_titles


def test_employee_cannot_retrieve_another_users_context(client, floor_headers):
    response = client.get("/api/work-context/emp-pm", headers=floor_headers)
    assert response.status_code == 403


def test_recent_enterprise_history_influences_recommendation_without_becoming_memory(client):
    purchasing = context(client, "emp-pm")
    recommendation = purchasing["recommended_actions"][0]["detail"]
    assert "Supplier Y recently reported another delay" in recommendation
    assert any(item["source"] == "Outlook" and "delay" in item["detail"]
               for item in purchasing["recent_context"])
    assert all("delayed and will not arrive until Tuesday" not in item["content"]
               for item in purchasing["long_term_memory"])


def test_long_term_memory_persists_across_agent_sessions():
    with SessionLocal() as first_session:
        MemoryService(first_session).remember(
            "emp-floor", "ongoing_project", "Own the Line 4 readiness checklist.",
            "approved_user_statement", 0.8,
        )
    with SessionLocal() as second_session:
        employee = second_session.get(Employee, "emp-floor")
        result = ContextService(second_session).work_context(employee)
        assert any(item["content"] == "Own the Line 4 readiness checklist."
                   for item in result["long_term_memory"])


def test_different_roles_produce_different_recommendations(client):
    purchasing = context(client, "emp-pm")["recommended_actions"][0]
    floor = context(client, "emp-floor")["recommended_actions"][0]
    executive = context(client, "emp-exec")["recommended_actions"][0]
    assert len({purchasing["title"], floor["title"], executive["title"]}) == 3
    assert purchasing["action"] == "RUN_PROACTIVE_ANALYSIS"
    assert floor["action"] == "CONTACT_PURCHASING"
    assert executive["action"] == "REVIEW_RISK"


def test_raw_outlook_and_teams_data_is_not_automatically_persisted_as_memory(client):
    with SessionLocal() as db:
        before = db.scalar(select(func.count()).select_from(Memory))
        raw_fragments = [email.body for email in db.scalars(select(Email)).all()]
        raw_fragments += [meeting.summary for meeting in db.scalars(select(TeamsMeeting)).all()]
    context(client, "emp-pm")
    context(client, "emp-floor")
    context(client, "emp-exec")
    with SessionLocal() as db:
        after = db.scalar(select(func.count()).select_from(Memory))
        memories = [memory.content for memory in db.scalars(select(Memory)).all()]
    assert after == before
    assert not any(fragment in memories for fragment in raw_fragments)

