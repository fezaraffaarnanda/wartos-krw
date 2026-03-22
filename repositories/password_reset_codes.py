"""
Repository untuk tabel password_reset_codes.
"""

from typing import Any

from repositories.base import BaseRepository


class PasswordResetCodeRepository(BaseRepository):
    """Akses data kode reset password."""

    def list_active_code_user_ids(self, now_iso: str) -> set[int]:
        result = (
            self._supabase.table("password_reset_codes")
            .select("user_id, expires_at")
            .is_("used_at", "null")
            .gt("expires_at", now_iso)
            .execute()
        )
        rows = result.data or []
        return {int(row["user_id"]) for row in rows if isinstance(row, dict) and row.get("user_id") is not None}

    def get_valid_code(self, user_id: int | str, code_hash: str, now_iso: str) -> dict[str, Any] | None:
        result = (
            self._supabase.table("password_reset_codes")
            .select("id, expires_at")
            .eq("user_id", user_id)
            .eq("code_hash", code_hash)
            .is_("used_at", "null")
            .gt("expires_at", now_iso)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        first = result.data[0]
        return first if isinstance(first, dict) else None

    def mark_code_used(self, code_id: int | str, used_at_iso: str) -> None:
        self._supabase.table("password_reset_codes").update(
            {"used_at": used_at_iso}
        ).eq("id", code_id).execute()

    def delete_codes_by_user_id(self, user_id: int | str) -> None:
        self._supabase.table("password_reset_codes").delete().eq("user_id", user_id).execute()

    def create_code(self, user_id: int | str, code_hash: str, expires_at_iso: str) -> None:
        self._supabase.table("password_reset_codes").insert(
            {
                "user_id": user_id,
                "code_hash": code_hash,
                "expires_at": expires_at_iso,
            }
        ).execute()
