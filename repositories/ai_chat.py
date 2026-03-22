"""
Repository AI chat.
"""

from datetime import datetime, timezone
from typing import Any

from repositories.base import BaseRepository


class AIChatRepository(BaseRepository):
    """Akses data session dan message AI chat."""

    def get_or_create_chat_session(self, user_id: int) -> dict[str, Any]:
        result = (
            self._supabase.table("ai_chat_sessions")
            .select("id, user_id, title, created_at, updated_at")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]

        created = (
            self._supabase.table("ai_chat_sessions")
            .insert({"user_id": user_id, "title": "Percakapan AI"})
            .execute()
        )
        return created.data[0]

    def create_chat_session(self, user_id: int) -> dict[str, Any]:
        created = (
            self._supabase.table("ai_chat_sessions")
            .insert({"user_id": user_id, "title": "Percakapan AI"})
            .execute()
        )
        return created.data[0]

    def get_chat_session_owned(self, user_id: int, session_id: int) -> dict[str, Any] | None:
        try:
            result = (
                self._supabase.table("ai_chat_sessions")
                .select("id, user_id, title, created_at, updated_at")
                .eq("id", session_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            )
            return result.data
        except Exception:
            return None

    def load_chat_history(self, session_id: int, limit: int = 30) -> list[dict[str, Any]]:
        result = (
            self._supabase.table("ai_chat_messages")
            .select("id, role, content, citations_json, created_at")
            .eq("session_id", session_id)
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        )
        return result.data or []

    def save_chat_message(
        self,
        session_id: int,
        role: str,
        content: str,
        citations: list[dict[str, Any]] | None = None,
    ) -> None:
        self._supabase.table("ai_chat_messages").insert(
            {
                "session_id": session_id,
                "role": role,
                "content": content,
                "citations_json": citations or [],
            }
        ).execute()
        self.touch_chat_session(session_id)

    def clear_chat_messages(self, session_id: int) -> None:
        self._supabase.table("ai_chat_messages").delete().eq("session_id", session_id).execute()

    def touch_chat_session(self, session_id: int) -> None:
        self._supabase.table("ai_chat_sessions").update(
            {"updated_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", session_id).execute()


def _get_or_create_chat_session(user_id: int) -> dict[str, Any]:
    """Ambil session terbaru milik user, buat baru jika belum ada."""
    return AIChatRepository().get_or_create_chat_session(user_id)


def _create_chat_session(user_id: int) -> dict[str, Any]:
    return AIChatRepository().create_chat_session(user_id)


def _get_chat_session_owned(user_id: int, session_id: int) -> dict[str, Any] | None:
    return AIChatRepository().get_chat_session_owned(user_id, session_id)


def _load_chat_history(session_id: int, limit: int = 30) -> list[dict[str, Any]]:
    return AIChatRepository().load_chat_history(session_id, limit=limit)


def _save_chat_message(
    session_id: int,
    role: str,
    content: str,
    citations: list[dict[str, Any]] | None = None,
) -> None:
    AIChatRepository().save_chat_message(
        session_id,
        role,
        content,
        citations=citations,
    )
