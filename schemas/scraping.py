"""
Schema payload scraping.
"""

from typing import Any, Mapping

from pydantic import BaseModel, Field


class ScrapeTriggerPayload(BaseModel):
    """Payload trigger scraping."""

    max_articles: int = Field(default=150, ge=1, le=999)

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> "ScrapeTriggerPayload":
        raw = str(body.get("max_articles", 150)).strip()
        if not raw.isdigit():
            value = 150
        else:
            value = max(1, min(int(raw), 999))
        return cls.model_validate({"max_articles": value})
