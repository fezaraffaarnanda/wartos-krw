"""
Repository versi system prompt classifier relevance (tabel relevance_prompts).
"""

import re
from typing import Any

from repositories.base import BaseRepository

_VERSION_RE = re.compile(r"^rel-v(\d+)$")


class RelevancePromptRepository(BaseRepository):
    """Akses data versi prompt relevance. Satu row is_active=true (partial unique index)."""

    def get_active(self) -> dict[str, Any] | None:
        try:
            result = (
                self._supabase.table("relevance_prompts")
                .select("version, prompt_text, created_by, created_at, notes")
                .eq("is_active", True)
                .limit(1)
                .execute()
            )
            rows = result.data or []
            return rows[0] if rows else None
        except Exception as exc:
            print(f"[RelevancePrompt] Gagal ambil prompt aktif: {exc}")
            return None

    def list_versions(self) -> list[dict[str, Any]]:
        try:
            result = (
                self._supabase.table("relevance_prompts")
                .select("version, is_active, created_by, created_at, notes")
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

    def insert_and_activate(
        self,
        *,
        version: str,
        prompt_text: str,
        created_by: str,
        notes: str = "",
    ) -> dict[str, Any] | None:
        """Nonaktifkan semua versi lalu insert versi baru sebagai aktif."""
        try:
            (
                self._supabase.table("relevance_prompts")
                .update({"is_active": False})
                .eq("is_active", True)
                .execute()
            )
            result = (
                self._supabase.table("relevance_prompts")
                .insert({
                    "version":     version,
                    "prompt_text": prompt_text,
                    "is_active":   True,
                    "created_by":  created_by,
                    "notes":       notes,
                })
                .execute()
            )
            rows = result.data or []
            return rows[0] if rows else None
        except Exception as exc:
            print(f"[RelevancePrompt] Gagal insert versi {version}: {exc}")
            return None
