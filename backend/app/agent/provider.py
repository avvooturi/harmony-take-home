from abc import ABC, abstractmethod
import json
import re

import httpx

from ..config import settings


class LLMProvider(ABC):
    name = "unknown"

    @abstractmethod
    def generate(self, prompt: str, system_prompt: str | None = None) -> str: ...

    @property
    def model(self) -> str:
        return "unknown"


class OllamaProvider(LLMProvider):
    name = "ollama"

    @property
    def model(self) -> str:
        return settings.ollama_model

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        response = httpx.post(f"{settings.ollama_url}/api/generate",
                              json={"model": settings.ollama_model, "prompt": prompt,
                                    "system": system_prompt or "", "stream": False},
                              timeout=settings.ollama_timeout_seconds)
        response.raise_for_status()
        content = response.json().get("response")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Local model returned an empty or malformed response")
        return content.strip()


class DeterministicProvider(LLMProvider):
    """Stable demo fallback; it recommends but never authorizes or executes."""

    name = "deterministic"

    @property
    def model(self) -> str:
        return "rules-v1"

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        if system_prompt:
            return self._chat_response(prompt)
        return ("Part X will likely cause Production Order 4812 to miss its scheduled date. "
                "Supplier Y said the shipment is delayed until Tuesday. Supplier Z can deliver sooner. "
                "I recommend moving PO-1007 to Supplier Z and notifying production. Would you like me to proceed?")

    @staticmethod
    def _chat_response(prompt: str) -> str:
        question_match = re.search(r"USER QUESTION:\n(.*?)\n\nAUTHORIZED CONTEXT:", prompt, re.S)
        question = question_match.group(1).strip() if question_match else prompt.strip()
        context_match = re.search(r"AUTHORIZED CONTEXT:\n(.*)$", prompt, re.S)
        try:
            context = json.loads(context_match.group(1)) if context_match else {}
        except json.JSONDecodeError:
            context = {}
        normalized = question.lower()
        words = re.findall(r"[a-z]+", normalized)
        if len(words) < 2 or not any(token in normalized for token in (
            "what", "why", "how", "help", "focus", "today", "risk", "part", "order",
            "supplier", "inventory", "approval", "work", "email", "meeting",
        )):
            return "I’m not sure what you’d like help with. Could you clarify the work question or task you want me to review?"
        if "focus" in normalized or "today" in normalized:
            items = context.get("current_work", [])[:3]
            if not items:
                return "I do not have enough authorized current-work context to identify today’s priorities."
            priorities = "; ".join(f"{item['title']}: {item['detail']}" for item in items)
            return f"Based on your authorized current work, focus on: {priorities}"
        if "part x" in normalized or "risk" in normalized or "supplier" in normalized:
            if context.get("employee", {}).get("role") != "Purchasing Manager":
                return ("Your authorized context shows a material concern affecting assigned work, but you do not "
                        "have purchasing authority. Review your assigned order and escalate the blocker to purchasing.")
            return ("Fact: Part X is projected to run out in five days and Production Order 4812 depends on it. "
                    "Recent authorized context includes Supplier Y’s delay, while durable memory identifies Supplier Z "
                    "as approved emergency coverage. Recommendation: prepare a supplier-change proposal and notify "
                    "production. I can suggest that action, but the application must authorize it and obtain approval.")
        return "I can help with the current work shown in your authorized context. Which item would you like me to explain or prioritize?"
