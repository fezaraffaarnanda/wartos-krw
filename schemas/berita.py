"""
Schema query params untuk endpoint berita.
"""

from typing import Any, Mapping

from pydantic import BaseModel, Field

_SORT_MAP = {
    "date": "date_parsed",
    "date_parsed": "date_parsed",
    "title": "title",
    "source": "source",
    "tags": "tags",
    "created_at": "created_at",
}

_ARCHIVE_STATUS_VALUES = {"active", "archived", "all"}


def _safe_int(raw: str, *, default: int, min_value: int, max_value: int) -> int:
    value = str(raw or "").strip()
    if not value or not value.isdigit():
        return default
    return max(min_value, min(int(value), max_value))


class BeritaFilterQuery(BaseModel):
    """Normalisasi query params endpoint berita agar konsisten."""

    search: str = Field(default="")
    date_from: str = Field(default="")
    date_to: str = Field(default="")
    kbli_code: str = Field(default="")
    aktivitas_code: str = Field(default="")
    archive_status: str = Field(default="active")
    page: int = Field(default=1, ge=1, le=50000)
    per_page: int = Field(default=15, ge=1, le=100)
    sort_by: str = Field(default="date_parsed")
    sort_dir: str = Field(default="desc")

    @classmethod
    def from_request_args(cls, args: Mapping[str, Any]) -> "BeritaFilterQuery":
        payload = {
            "search": str(args.get("search", "")).strip(),
            "date_from": str(args.get("date_from", "")).strip(),
            "date_to": str(args.get("date_to", "")).strip(),
            "kbli_code": str(args.get("kbli_code", "")).strip().upper(),
            "aktivitas_code": str(args.get("aktivitas_code", "")).strip(),
            "archive_status": _normalize_archive_status(args.get("archive_status", "active")),
            "page": _safe_int(
                str(args.get("page", "")),
                default=1,
                min_value=1,
                max_value=50000,
            ),
            "per_page": _safe_int(
                str(args.get("per_page", "")),
                default=15,
                min_value=1,
                max_value=100,
            ),
            "sort_by": str(args.get("sort_by", "date_parsed")).strip().lower(),
            "sort_dir": str(args.get("sort_dir", "desc")).strip().lower(),
        }
        return cls.model_validate(payload)

    def resolve_sort(self) -> tuple[str, bool, str]:
        sort_col = _SORT_MAP.get(self.sort_by, "date_parsed")
        sort_desc = self.sort_dir != "asc"
        normalized_dir = "desc" if sort_desc else "asc"
        return sort_col, sort_desc, normalized_dir


class BeritaArchivePayload(BaseModel):
    is_archived: bool = Field(default=False)

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> "BeritaArchivePayload":
        return cls.model_validate({
            "is_archived": bool(body.get("is_archived", False)),
        })


class BeritaClassificationPayload(BaseModel):
    kbli_code: str = Field(default="")
    aktivitas_code: str = Field(default="")

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> "BeritaClassificationPayload":
        return cls.model_validate(
            {
                "kbli_code": str(body.get("kbli_code", "")).strip().upper(),
                "aktivitas_code": str(body.get("aktivitas_code", "")).strip(),
            }
        )


def _normalize_archive_status(raw: Any) -> str:
    value = str(raw or "active").strip().lower()
    if value in _ARCHIVE_STATUS_VALUES:
        return value
    return "active"
