"""
Repository counter aktivitas pengguna (tabel user_activity_state), dipakai
memicu prompt feedback. Angka BERASAL DARI KLIEN -- lihat komentar migrasi
20260819_create_user_activity_state.sql.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from repositories.base import BaseRepository


class UserActivityRepository(BaseRepository):
    """Akses state aktivitas per user. Fail-soft di semua method -- tracking
    tidak boleh menggagalkan request pemanggilnya."""

    def bump(self, *, user_id: int, event_type: str) -> dict[str, Any] | None:
        try:
            result = self._supabase.rpc("bump_user_activity", {
                "p_user_id": user_id,
                "p_event_type": event_type,
            }).execute()
            data = result.data
            if isinstance(data, list):
                return data[0] if data else None
            return data
        except Exception as exc:
            print(f"[UserActivity] Gagal bump user {user_id}: {exc}")
            return None

    def get_state(self, user_id: int) -> dict[str, Any] | None:
        try:
            result = (
                self._supabase.table("user_activity_state")
                .select("*")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            rows = result.data or []
            return rows[0] if rows else None
        except Exception as exc:
            print(f"[UserActivity] Gagal ambil state user {user_id}: {exc}")
            return None

    def snooze(self, *, user_id: int, days: int) -> dict[str, Any] | None:
        """Tunda prompt `days` hari ke depan dan naikkan prompt_dismiss_count.

        Baca-lalu-tulis (bukan RPC): dismiss adalah aksi manusia sesekali,
        bukan jalur panas berkecepatan tinggi seperti bump_user_activity, jadi
        race antar tab tidak jadi masalah nyata di sini.
        """
        current = self.get_state(user_id)
        if current is None:
            return None
        dismiss_count = int(current.get("prompt_dismiss_count") or 0) + 1
        until = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
        try:
            result = (
                self._supabase.table("user_activity_state")
                .update({
                    "prompt_snoozed_until": until,
                    "prompt_dismiss_count": dismiss_count,
                })
                .eq("user_id", user_id)
                .execute()
            )
            rows = result.data or []
            return rows[0] if rows else None
        except Exception as exc:
            print(f"[UserActivity] Gagal snooze user {user_id}: {exc}")
            return None

    def mark_submitted(self, *, user_id: int, snooze_days: int = 90) -> dict[str, Any] | None:
        until = (datetime.now(timezone.utc) + timedelta(days=snooze_days)).isoformat()
        try:
            result = (
                self._supabase.table("user_activity_state")
                .update({
                    "feedback_submitted_at": datetime.now(timezone.utc).isoformat(),
                    "prompt_snoozed_until": until,
                })
                .eq("user_id", user_id)
                .execute()
            )
            rows = result.data or []
            return rows[0] if rows else None
        except Exception as exc:
            print(f"[UserActivity] Gagal tandai submitted user {user_id}: {exc}")
            return None
