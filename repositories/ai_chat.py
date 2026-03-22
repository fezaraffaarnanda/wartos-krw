"""
Repository AI chat.
"""

from datetime import datetime, timezone

from clients.supabase import supabase


def _get_or_create_chat_session(user_id: int) -> dict:
    """Ambil session terbaru milik user, atau buat baru jika belum ada."""
    result = (
        supabase.table("ai_chat_sessions")
        .select("id, user_id, title, created_at, updated_at")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]

    created = (
        supabase.table("ai_chat_sessions")
        .insert({"user_id": user_id, "title": "Percakapan AI"})
        .execute()
    )
    return created.data[0]


def _create_chat_session(user_id: int) -> dict:
    created = (
        supabase.table("ai_chat_sessions")
        .insert({"user_id": user_id, "title": "Percakapan AI"})
        .execute()
    )
    return created.data[0]


def _get_chat_session_owned(user_id: int, session_id: int) -> dict | None:
    try:
        result = (
            supabase.table("ai_chat_sessions")
            .select("id, user_id, title, created_at, updated_at")
            .eq("id", session_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        return result.data
    except Exception:
        return None


def _load_chat_history(session_id: int, limit: int = 30) -> list[dict]:
    result = (
        supabase.table("ai_chat_messages")
        .select("id, role, content, citations_json, created_at")
        .eq("session_id", session_id)
        .order("created_at", desc=False)
        .limit(limit)
        .execute()
    )
    return result.data or []


def _save_chat_message(
    session_id: int,
    role: str,
    content: str,
    citations: list[dict] | None = None,
) -> None:
    supabase.table("ai_chat_messages").insert({
        "session_id": session_id,
        "role": role,
        "content": content,
        "citations_json": citations or [],
    }).execute()

    supabase.table("ai_chat_sessions").update({
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", session_id).execute()
