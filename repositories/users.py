"""
Repository untuk manajemen tabel users.
"""

from typing import Any

from repositories.base import BaseRepository


class UserRepository(BaseRepository):
    """Akses data user dengan Supabase fluent API."""

    def get_user_by_id(self, user_id: int | str) -> dict[str, Any] | None:
        try:
            result = (
                self._supabase.table("users")
                .select("id, username, role, must_change_password, created_at")
                .eq("id", user_id)
                .single()
                .execute()
            )
            return result.data
        except Exception:
            return None

    def get_user_auth_by_username(self, username: str) -> dict[str, Any] | None:
        try:
            result = (
                self._supabase.table("users")
                .select("id, username, password_hash, role, must_change_password")
                .eq("username", username)
                .single()
                .execute()
            )
            return result.data
        except Exception:
            return None

    def get_user_password_by_id(self, user_id: int | str) -> dict[str, Any] | None:
        try:
            result = (
                self._supabase.table("users")
                .select("id, username, password_hash")
                .eq("id", user_id)
                .single()
                .execute()
            )
            return result.data
        except Exception:
            return None

    def get_user_basic_by_username(self, username: str) -> dict[str, Any] | None:
        try:
            result = (
                self._supabase.table("users")
                .select("id, username")
                .eq("username", username)
                .single()
                .execute()
            )
            return result.data
        except Exception:
            return None

    def list_users(self) -> list[dict[str, Any]]:
        result = (
            self._supabase.table("users")
            .select("id, username, role, must_change_password, created_at")
            .order("created_at", desc=False)
            .execute()
        )
        return result.data or []

    def username_exists(self, username: str) -> bool:
        result = (
            self._supabase.table("users")
            .select("id")
            .eq("username", username)
            .limit(1)
            .execute()
        )
        return bool(result.data)

    def create_user(
        self,
        *,
        username: str,
        password_hash: str,
        role: str,
        must_change_password: bool,
    ) -> dict[str, Any] | None:
        result = (
            self._supabase.table("users")
            .insert(
                {
                    "username": username,
                    "password_hash": password_hash,
                    "role": role,
                    "must_change_password": must_change_password,
                }
            )
            .execute()
        )
        if not result.data:
            return None
        first = result.data[0]
        return first if isinstance(first, dict) else None

    def delete_user(self, user_id: int) -> None:
        self._supabase.table("users").delete().eq("id", user_id).execute()

    def update_password(self, user_id: int | str, password_hash: str, must_change_password: bool) -> None:
        self._supabase.table("users").update(
            {
                "password_hash": password_hash,
                "must_change_password": must_change_password,
            }
        ).eq("id", user_id).execute()
