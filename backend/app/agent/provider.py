from abc import ABC, abstractmethod
import json
import re
import threading
import time
from dataclasses import dataclass

import httpx

from ..config import settings


@dataclass(frozen=True)
class ProviderAvailability:
    available: bool
    detail: str | None = None


class LLMProvider(ABC):
    name = "unknown"

    @abstractmethod
    def generate(self, prompt: str, system_prompt: str | None = None) -> str: ...

    @property
    def model(self) -> str:
        return "unknown"

    def availability(self) -> ProviderAvailability:
        return ProviderAvailability(True)

    def mark_unavailable(self, detail: str) -> None:
        return None


class OllamaProvider(LLMProvider):
    name = "ollama"
    _availability_cache: dict[tuple[str, str], tuple[float, ProviderAvailability]] = {}
    _cache_lock = threading.Lock()

    @property
    def model(self) -> str:
        return settings.ollama_model

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        response = httpx.post(f"{settings.ollama_url}/api/generate",
                              json={"model": settings.ollama_model, "prompt": prompt,
                                    "system": system_prompt or "", "stream": False,
                                    "keep_alive": "10m",
                                    "options": {"num_predict": settings.ollama_max_output_tokens,
                                                "temperature": 0.2}},
                              timeout=settings.ollama_timeout_seconds)
        response.raise_for_status()
        content = response.json().get("response")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Local model returned an empty or malformed response")
        return content.strip()

    def availability(self) -> ProviderAvailability:
        key = (settings.ollama_url, settings.ollama_model)
        current_time = time.monotonic()
        with self._cache_lock:
            cached = self._availability_cache.get(key)
            if cached and cached[0] > current_time:
                return cached[1]
        try:
            response = httpx.get(f"{settings.ollama_url}/api/tags",
                                 timeout=settings.ollama_health_timeout_seconds)
            response.raise_for_status()
            models = {item.get("name") for item in response.json().get("models", [])}
            models.update(item.get("model") for item in response.json().get("models", []))
            if settings.ollama_model not in models:
                result = ProviderAvailability(
                    False, f"Configured model {settings.ollama_model} is not installed")
            else:
                result = ProviderAvailability(True)
        except Exception as exc:
            result = ProviderAvailability(False, f"Ollama health check failed: {type(exc).__name__}")
        ttl = settings.ollama_unavailable_cache_seconds if not result.available else 2.0
        with self._cache_lock:
            self._availability_cache[key] = (current_time + ttl, result)
        return result

    def mark_unavailable(self, detail: str) -> None:
        key = (settings.ollama_url, settings.ollama_model)
        result = ProviderAvailability(False, detail)
        with self._cache_lock:
            self._availability_cache[key] = (
                time.monotonic() + settings.ollama_failure_cache_seconds, result)

    @classmethod
    def clear_availability_cache(cls) -> None:
        with cls._cache_lock:
            cls._availability_cache.clear()


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
        recognized_terms = (
            "what", "why", "how", "help", "focus", "today", "risk", "part", "order",
            "supplier", "inventory", "approval", "pending", "work", "task", "priority",
            "prioritize", "recommend", "action", "email", "meeting", "delay", "production",
            "impact",
        )
        if len(words) < 2 or not any(token in normalized for token in recognized_terms):
            return "I’m not sure what you’d like help with. Could you clarify the work question or task you want me to review?"
        if any(token in normalized for token in ("focus", "today", "priority", "prioritize")):
            items = context.get("current_work", [])[:3]
            if not items:
                return "I do not have enough authorized current-work context to identify today’s priorities."
            priorities = "; ".join(f"{item['title']}: {item['detail']}" for item in items)
            return f"Based on your authorized current work, focus on: {priorities}"
        if "current task" in normalized or "my task" in normalized or "current work" in normalized:
            items = context.get("current_work", [])
            if not items:
                return "I do not have any authorized current tasks to summarize."
            tasks = "; ".join(f"{item['title']} ({item.get('status', 'ACTIVE')})" for item in items)
            return f"Your current authorized tasks are: {tasks}."
        if any(token in normalized for token in (
            "part x", "risk", "supplier delay", "production impact", "part x problem",
        )):
            if context.get("employee", {}).get("role") != "Purchasing Manager":
                return ("Your authorized context shows a material concern affecting assigned work, but you do not "
                        "have purchasing authority. Review your assigned order and escalate the blocker to purchasing.")
            return ("Fact: Part X is projected to run out in five days and Production Order 4812 depends on it. "
                    "Recent authorized context includes Supplier Y’s delay, while durable memory identifies Supplier Z "
                    "as approved emergency coverage. Recommendation: prepare a supplier-change proposal and notify "
                    "production. I can suggest that action, but the application must authorize it and obtain approval.")
        if "recommend" in normalized or "action" in normalized:
            actions = context.get("recommended_actions", [])
            if actions:
                return "; ".join(f"{item['title']}: {item['detail']}" for item in actions)
            return "I do not have a supported recommended action in the authorized context for this request."
        if "approval" in normalized or "pending" in normalized:
            pending = [item for item in context.get("current_work", []) if item.get("status") == "PENDING"]
            if pending:
                return "There is a pending approval ready for review in the Approvals page. Chat cannot approve or execute it."
            return "There are no pending approvals in your authorized current context."
        return "I can help with the current work shown in your authorized context. Which item would you like me to explain or prioritize?"
