"""
Schema payload & query untuk fitur feedback pengguna.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, Field

_CATEGORY_VALUES = ("berita", "ai_chat", "ai_insight", "statistik_resmi", "scraping", "lainnya")
_EVENT_TYPE_VALUES = (
    "berita_detail_open", "ai_chat_message", "ai_insight_generate", "scrape_run", "export_data",
)


def _safe_int(raw: Any, *, default: int, min_value: int, max_value: int) -> int:
    value = str(raw if raw is not None else "").strip()
    if not value or not value.lstrip("-").isdigit():
        return default
    return max(min_value, min(int(value), max_value))


class ActivityTrackPayload(BaseModel):
    """POST /api/activity/track. event_type WAJIB dari allowlist -- tanpa ini
    tipe apa pun bisa mengembang di kolom counts jsonb tanpa batas."""

    event_type: Literal[
        "berita_detail_open", "ai_chat_message", "ai_insight_generate", "scrape_run", "export_data",
    ]

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> "ActivityTrackPayload | None":
        raw = str(body.get("event_type", "")).strip()
        if raw not in _EVENT_TYPE_VALUES:
            return None
        return cls.model_validate({"event_type": raw})


class FeedbackSubmitPayload(BaseModel):
    """POST /api/feedback."""

    rating: int = Field(ge=1, le=5)
    category: Literal["berita", "ai_chat", "ai_insight", "statistik_resmi", "scraping", "lainnya"]
    comment: str = Field(default="", max_length=2000)
    page_path: str = Field(default="", max_length=200)
    trigger_source: Literal["sidebar", "auto_prompt"] = "sidebar"

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> "FeedbackSubmitPayload | None":
        raw_rating = str(body.get("rating", "")).strip()
        if raw_rating not in ("1", "2", "3", "4", "5"):
            return None
        rating = int(raw_rating)
        category = str(body.get("category", "")).strip().lower()
        if category not in _CATEGORY_VALUES:
            return None
        raw_source = str(body.get("trigger_source", "sidebar")).strip().lower()
        return cls.model_validate({
            "rating": rating,
            "category": category,
            "comment": str(body.get("comment", "")).strip()[:2000],
            "page_path": str(body.get("page_path", "")).strip()[:200],
            "trigger_source": raw_source if raw_source in ("sidebar", "auto_prompt") else "sidebar",
        })


class FeedbackListQuery(BaseModel):
    """GET /api/admin/feedback."""

    page: int = Field(default=1, ge=1, le=5000)
    per_page: int = Field(default=20, ge=1, le=100)
    category: str = Field(default="")
    min_rating: int | None = Field(default=None, ge=1, le=5)

    @classmethod
    def from_request_args(cls, args: Mapping[str, Any]) -> "FeedbackListQuery":
        raw_category = str(args.get("category", "")).strip().lower()
        min_rating_raw = str(args.get("min_rating", "")).strip()
        return cls.model_validate({
            "page": _safe_int(args.get("page"), default=1, min_value=1, max_value=5000),
            "per_page": _safe_int(args.get("per_page"), default=20, min_value=1, max_value=100),
            "category": raw_category if raw_category in _CATEGORY_VALUES else "",
            "min_rating": int(min_rating_raw) if min_rating_raw in ("1", "2", "3", "4", "5") else None,
        })
