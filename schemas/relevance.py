"""
Schema payload & query untuk audit classifier relevance (tahap-1).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, Field

_QUEUE_MODES = ("uncertainty", "audit", "failed", "labeled", "disagreement", "all")


def _safe_int(raw: Any, *, default: int, min_value: int, max_value: int) -> int:
    value = str(raw if raw is not None else "").strip()
    if not value or not value.lstrip("-").isdigit():
        return default
    return max(min_value, min(int(value), max_value))


class RelevanceQueueQuery(BaseModel):
    """Query param antrian review GET /api/admin/relevance/review-queue."""

    mode: Literal["uncertainty", "audit", "failed", "labeled", "disagreement", "all"] = "uncertainty"
    page: int = Field(default=1, ge=1, le=50000)
    per_page: int = Field(default=25, ge=1, le=100)
    search: str = Field(default="", max_length=200)
    source: str = Field(default="", max_length=100)
    score_min: int | None = Field(default=None, ge=0, le=100)
    score_max: int | None = Field(default=None, ge=0, le=100)

    @classmethod
    def from_request_args(cls, args: Mapping[str, Any]) -> "RelevanceQueueQuery":
        raw_mode = str(args.get("mode", "uncertainty")).strip().lower()
        score_min_raw = str(args.get("score_min", "")).strip()
        score_max_raw = str(args.get("score_max", "")).strip()
        return cls.model_validate({
            "mode": raw_mode if raw_mode in _QUEUE_MODES else "uncertainty",
            "page": _safe_int(args.get("page"), default=1, min_value=1, max_value=50000),
            "per_page": _safe_int(args.get("per_page"), default=25, min_value=1, max_value=100),
            "search": str(args.get("search", "")).strip(),
            "source": str(args.get("source", "")).strip(),
            "score_min": int(score_min_raw) if score_min_raw.isdigit() else None,
            "score_max": int(score_max_raw) if score_max_raw.isdigit() else None,
        })


class HumanLabelPayload(BaseModel):
    """PATCH /api/admin/berita/<id>/human-label."""

    is_relevant: bool
    label_source: Literal["audit", "targeted", "failure_triage"] = "targeted"
    note: str = Field(default="", max_length=500)

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> "HumanLabelPayload":
        raw_source = str(body.get("label_source", "targeted")).strip().lower()
        return cls.model_validate({
            "is_relevant": bool(body.get("is_relevant")),
            "label_source": raw_source if raw_source in ("audit", "targeted", "failure_triage") else "targeted",
            "note": str(body.get("note", "")).strip()[:500],
        })


class BulkLabelPayload(BaseModel):
    """POST /api/admin/relevance/bulk-label.

    berita_ids boleh kosong setelah sanitasi (semua entri tak valid) --
    service layer yang menolak dengan pesan bersih, bukan pydantic, supaya
    konsisten dengan cara list ini di-cap ke 50 di classmethod, bukan di Field.
    """

    berita_ids: list[int] = Field(max_length=50)
    is_relevant: bool
    label_source: Literal["targeted", "failure_triage"] = "targeted"

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> "BulkLabelPayload":
        raw_ids = body.get("berita_ids") or []
        ids: list[int] = []
        if isinstance(raw_ids, list):
            for item in raw_ids:
                try:
                    ids.append(int(item))
                except (TypeError, ValueError):
                    continue
        raw_source = str(body.get("label_source", "targeted")).strip().lower()
        return cls.model_validate({
            "berita_ids": ids[:50],
            "is_relevant": bool(body.get("is_relevant")),
            "label_source": raw_source if raw_source in ("targeted", "failure_triage") else "targeted",
        })


class ReclassifyBulkPayload(BaseModel):
    """POST /api/admin/relevance/reclassify-bulk."""

    berita_ids: list[int] = Field(default_factory=list, max_length=25)
    limit: int = Field(default=25, ge=1, le=25)

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> "ReclassifyBulkPayload":
        raw_ids = body.get("berita_ids") or []
        ids: list[int] = []
        if isinstance(raw_ids, list):
            for item in raw_ids:
                try:
                    ids.append(int(item))
                except (TypeError, ValueError):
                    continue
        return cls.model_validate({
            "berita_ids": ids[:25],
            "limit": _safe_int(body.get("limit"), default=25, min_value=1, max_value=25),
        })


class AuditSamplePayload(BaseModel):
    """POST /api/admin/relevance/audit-sample."""

    per_band: int = Field(default=20, ge=5, le=60)

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> "AuditSamplePayload":
        return cls.model_validate({
            "per_band": _safe_int(body.get("per_band"), default=20, min_value=5, max_value=60),
        })


class PromptDraftPayload(BaseModel):
    """POST /api/admin/relevance/prompt-draft."""

    limit: int = Field(default=20, ge=5, le=50)

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> "PromptDraftPayload":
        return cls.model_validate({
            "limit": _safe_int(body.get("limit"), default=20, min_value=5, max_value=50),
        })


class PromptEvalPayload(BaseModel):
    """POST /api/admin/relevance/prompt-eval."""

    draft_prompt: str = Field(min_length=200)
    sample_size: int = Field(default=40, ge=10, le=60)

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> "PromptEvalPayload":
        return cls.model_validate({
            "draft_prompt": str(body.get("draft_prompt", "")).strip(),
            "sample_size": _safe_int(body.get("sample_size"), default=40, min_value=10, max_value=60),
        })


class PromptApplyPayload(BaseModel):
    """POST /api/admin/relevance/prompt-apply."""

    draft_prompt: str = Field(min_length=200)
    confirmation: str = Field(default="")
    notes: str = Field(default="", max_length=2000)
    eval_result: dict[str, Any] | None = None

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> "PromptApplyPayload":
        eval_result = body.get("eval_result")
        return cls.model_validate({
            "draft_prompt": str(body.get("draft_prompt", "")).strip(),
            "confirmation": str(body.get("confirmation", "")).strip(),
            "notes": str(body.get("notes", "")).strip()[:2000],
            "eval_result": eval_result if isinstance(eval_result, dict) else None,
        })


class PromptRollbackPayload(BaseModel):
    """POST /api/admin/relevance/prompt-rollback."""

    version: str = Field(pattern=r"^rel-v\d+$")
    confirmation: str = Field(default="")

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> "PromptRollbackPayload":
        return cls.model_validate({
            "version": str(body.get("version", "")).strip(),
            "confirmation": str(body.get("confirmation", "")).strip(),
        })


class FewShotExportQuery(BaseModel):
    """GET /api/admin/relevance/few-shot-export."""

    limit: int = Field(default=20, ge=5, le=50)

    @classmethod
    def from_request_args(cls, args: Mapping[str, Any]) -> "FewShotExportQuery":
        return cls.model_validate({
            "limit": _safe_int(args.get("limit"), default=20, min_value=5, max_value=50),
        })


class RelevanceMetricsQuery(BaseModel):
    """GET /api/admin/relevance/metrics."""

    prompt_version: str | None = Field(default=None, pattern=r"^rel-v\d+$")

    @classmethod
    def from_request_args(cls, args: Mapping[str, Any]) -> "RelevanceMetricsQuery":
        raw = str(args.get("prompt_version", "")).strip()
        return cls.model_validate({"prompt_version": raw or None})
