from typing import Any

from pydantic import BaseModel


class Decision(BaseModel):
    decision: str


class ChatRequest(BaseModel):
    message: str


class ToolRequest(BaseModel):
    name: str
    arguments: dict[str, Any]


def serialize(obj, fields: list[str]) -> dict:
    result = {}
    for field in fields:
        value = getattr(obj, field)
        result[field] = value.isoformat() if hasattr(value, "isoformat") else value
    return result

