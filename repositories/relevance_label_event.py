"""
Repository riwayat label manusia classifier relevance (tabel relevance_label_events).
"""

from typing import Any

from repositories.base import BaseRepository


class RelevanceLabelEventRepository(BaseRepository):
    """Akses riwayat perubahan human_label — dipakai undo, provenance, dan metrik per versi prompt."""

    def record(
        self,
        *,
        berita_id: int,
        previous_label: bool | None,
        new_label: bool | None,
        label_source: str,
        note: str,
        machine_label: bool | None,
        machine_score: int | None,
        prompt_version: str | None,
        actor_username: str,
    ) -> dict[str, Any] | None:
        try:
            result = (
                self._supabase.table("relevance_label_events")
                .insert({
                    "berita_id": berita_id,
                    "previous_label": previous_label,
                    "new_label": new_label,
                    "label_source": label_source,
                    "note": note or None,
                    "machine_label": machine_label,
                    "machine_score": machine_score,
                    "prompt_version": prompt_version,
                    "actor_username": actor_username,
                })
                .execute()
            )
            rows = result.data or []
            return rows[0] if rows else None
        except Exception as exc:
            print(f"[RelevanceLabelEvent] Gagal catat event berita {berita_id}: {exc}")
            return None

    def list_for_berita(self, berita_id: int, *, limit: int = 20) -> list[dict[str, Any]]:
        try:
            result = (
                self._supabase.table("relevance_label_events")
                .select("*")
                .eq("berita_id", berita_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data or []
        except Exception as exc:
            print(f"[RelevanceLabelEvent] Gagal list event berita {berita_id}: {exc}")
            return []

    def last_event_for_actor(self, actor_username: str) -> dict[str, Any] | None:
        """Event terakhir milik actor — dipakai server-side undo lintas reload."""
        try:
            result = (
                self._supabase.table("relevance_label_events")
                .select("*")
                .eq("actor_username", actor_username)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            rows = result.data or []
            return rows[0] if rows else None
        except Exception as exc:
            print(f"[RelevanceLabelEvent] Gagal ambil event terakhir {actor_username}: {exc}")
            return None

    def count_since(self, *, actor_username: str, since_iso: str) -> int:
        try:
            result = (
                self._supabase.table("relevance_label_events")
                .select("id", count="exact")
                .eq("actor_username", actor_username)
                .gte("created_at", since_iso)
                .execute()
            )
            return result.count or 0
        except Exception as exc:
            print(f"[RelevanceLabelEvent] Gagal hitung event {actor_username}: {exc}")
            return 0
