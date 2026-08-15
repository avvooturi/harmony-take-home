from abc import ABC, abstractmethod

import httpx

from ..config import settings


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str: ...


class OllamaProvider(LLMProvider):
    def generate(self, prompt: str) -> str:
        response = httpx.post(f"{settings.ollama_url}/api/generate",
                              json={"model": settings.ollama_model, "prompt": prompt, "stream": False}, timeout=20)
        response.raise_for_status()
        return response.json()["response"]


class DeterministicProvider(LLMProvider):
    """Stable demo fallback; it recommends but never authorizes or executes."""

    def generate(self, prompt: str) -> str:
        return ("Part X will likely cause Production Order 4812 to miss its scheduled date. "
                "Supplier Y said the shipment is delayed until Tuesday. Supplier Z can deliver sooner. "
                "I recommend moving PO-1007 to Supplier Z and notifying production. Would you like me to proceed?")

