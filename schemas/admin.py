"""
Schema payload admin.
"""

from typing import Any, Mapping

from pydantic import BaseModel, Field


class CreateUserPayload(BaseModel):
    """Payload pembuatan user oleh admin."""

    username: str = Field(default="")

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> "CreateUserPayload":
        payload = {"username": str(body.get("username", "")).strip().lower()[:50]}
        return cls.model_validate(payload)
