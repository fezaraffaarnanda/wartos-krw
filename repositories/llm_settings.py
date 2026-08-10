"""
Repository setting provider LLM default (tabel llm_provider_settings, single-row id=1).
"""

from datetime import datetime, timezone
from typing import Any

from repositories.base import BaseRepository


class LlmSettingsRepository(BaseRepository):
    """Akses provider LLM default yang dikonfigurasi admin."""

    def get_provider(self) -> str | None:
        try:
            result = (
                self._supabase.table("llm_provider_settings")
                .select("provider")
                .eq("id", 1)
                .limit(1)
                .execute()
            )
            rows = result.data or []
            return rows[0]["provider"] if rows else None
        except Exception as exc:
            print(f"[LlmSettings] Gagal ambil provider aktif: {exc}")
            return None

    def set_provider(self, provider: str, updated_by: str) -> dict[str, Any] | None:
        try:
            result = (
                self._supabase.table("llm_provider_settings")
                .upsert({
                    "id":         1,
                    "provider":   provider,
                    "updated_by": updated_by,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })
                .execute()
            )
            rows = result.data or []
            return rows[0] if rows else None
        except Exception as exc:
            print(f"[LlmSettings] Gagal set provider ke {provider!r}: {exc}")
            return None
