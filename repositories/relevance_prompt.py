"""
Repository versi system prompt classifier relevance (tabel relevance_prompts).
"""

import re
from typing import Any

from repositories.base import BaseRepository

_VERSION_RE = re.compile(r"^rel-v(\d+)$")

_ACTIVE_COLUMNS = "version, prompt_text, created_by, created_at, notes, activated_at, eval_json"
_VERSION_LIST_COLUMNS = (
    "version, is_active, status, created_by, created_at, notes, "
    "activated_at, deactivated_at, eval_json, parent_version"
)


class RelevancePromptRepository(BaseRepository):
    """Akses data versi prompt relevance. Satu row is_active=true (partial unique index)."""

    def get_active_pointer(self) -> dict[str, Any] | None:
        """Ambil HANYA {id, version, activated_at} dari prompt aktif — tanpa
        prompt_text. Query murah untuk cek cache-busting antar worker."""
        try:
            result = (
                self._supabase.table("relevance_prompts")
                .select("id, version, activated_at")
                .eq("is_active", True)
                .limit(1)
                .execute()
            )
            rows = result.data or []
            return rows[0] if rows else None
        except Exception as exc:
            print(f"[RelevancePrompt] Gagal ambil pointer aktif: {exc}")
            return None

    def get_active(self) -> dict[str, Any] | None:
        try:
            result = (
                self._supabase.table("relevance_prompts")
                .select(_ACTIVE_COLUMNS)
                .eq("is_active", True)
                .limit(1)
                .execute()
            )
            rows = result.data or []
            return rows[0] if rows else None
        except Exception as exc:
            print(f"[RelevancePrompt] Gagal ambil prompt aktif: {exc}")
            return None

    def get_by_version(self, version: str) -> dict[str, Any] | None:
        try:
            result = (
                self._supabase.table("relevance_prompts")
                .select(_ACTIVE_COLUMNS)
                .eq("version", version)
                .limit(1)
                .execute()
            )
            rows = result.data or []
            return rows[0] if rows else None
        except Exception as exc:
            print(f"[RelevancePrompt] Gagal ambil versi {version}: {exc}")
            return None

    def list_versions(self) -> list[dict[str, Any]]:
        try:
            result = (
                self._supabase.table("relevance_prompts")
                .select(_VERSION_LIST_COLUMNS)
                .order("id", desc=True)
                .execute()
            )
            return result.data or []
        except Exception as exc:
            print(f"[RelevancePrompt] Gagal list versi: {exc}")
            return []

    def next_version(self) -> str:
        """Cari nomor versi tertinggi rel-vN → return rel-v(N+1)."""
        max_n = 1
        for row in self.list_versions():
            m = _VERSION_RE.match(str(row.get("version") or ""))
            if m:
                max_n = max(max_n, int(m.group(1)))
        return f"rel-v{max_n + 1}"

    def activate(
        self,
        *,
        version: str,
        prompt_text: str,
        created_by: str,
        notes: str = "",
        eval_result: dict[str, Any] | None = None,
        parent_version: str | None = None,
    ) -> dict[str, Any] | None:
        """Aktivasi atomik lewat RPC activate_relevance_prompt — menggantikan
        insert_and_activate() lama yang non-transaksional (deactivate lalu
        insert dua statement terpisah; insert gagal = nol prompt aktif)."""
        try:
            result = self._supabase.rpc("activate_relevance_prompt", {
                "p_version": version,
                "p_prompt_text": prompt_text,
                "p_created_by": created_by,
                "p_notes": notes,
                "p_eval": eval_result or {},
                "p_parent": parent_version,
            }).execute()
            data = result.data
            if isinstance(data, list):
                return data[0] if data else None
            return data
        except Exception as exc:
            print(f"[RelevancePrompt] Gagal aktivasi versi {version}: {exc}")
            return None

    def rollback_to(self, version: str) -> dict[str, Any] | None:
        """Rollback ke versi lama tanpa membuat versi baru, lewat RPC."""
        try:
            result = self._supabase.rpc("rollback_relevance_prompt", {
                "p_version": version,
            }).execute()
            data = result.data
            if isinstance(data, list):
                return data[0] if data else None
            return data
        except Exception as exc:
            print(f"[RelevancePrompt] Gagal rollback ke versi {version}: {exc}")
            return None
