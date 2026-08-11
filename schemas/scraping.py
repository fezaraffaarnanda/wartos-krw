"""
Schema payload scraping.
"""

from typing import Any, Mapping

from pydantic import BaseModel, Field


class NewsSourceOut(BaseModel):
    """Satu sumber berita untuk konsumsi frontend (GET /api/sources)."""

    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str


class ScrapeTriggerPayload(BaseModel):
    """Payload trigger scraping."""

    max_articles: int = Field(default=150, ge=1, le=5000)
    backfill: bool = Field(default=False)

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> "ScrapeTriggerPayload":
        raw = str(body.get("max_articles", 150)).strip()
        if not raw.isdigit():
            value = 150
        else:
            value = max(1, min(int(raw), 5000))
        backfill_raw = body.get("backfill", False)
        backfill = backfill_raw if isinstance(backfill_raw, bool) else str(backfill_raw).strip().lower() in ("1", "true", "yes")
        return cls.model_validate({"max_articles": value, "backfill": backfill})
