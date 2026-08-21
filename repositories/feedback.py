"""
Repository submission feedback pengguna (tabel feedback).
"""

from datetime import datetime, timezone
from typing import Any

from repositories.base import BaseRepository

_LIST_COLUMNS = (
    "id, username, role, rating, category, comment, page_path, trigger_source, created_at, "
    "status, admin_note, handled_by, handled_at"
)


class FeedbackRepository(BaseRepository):
    """Akses data feedback pengguna."""

    def insert_feedback(
        self,
        *,
        user_id: int,
        username: str,
        role: str,
        rating: int,
        category: str,
        comment: str,
        page_path: str,
        event_count_at_submit: int,
        trigger_source: str,
    ) -> dict[str, Any] | None:
        try:
            result = (
                self._supabase.table("feedback")
                .insert({
                    "user_id": user_id,
                    "username": username,
                    "role": role,
                    "rating": rating,
                    "category": category,
                    "comment": comment or None,
                    "page_path": page_path or None,
                    "event_count_at_submit": event_count_at_submit,
                    "trigger_source": trigger_source,
                })
                .execute()
            )
            rows = result.data or []
            return rows[0] if rows else None
        except Exception as exc:
            print(f"[Feedback] Gagal simpan feedback user {user_id}: {exc}")
            return None

    def list_feedback(
        self, *, page: int = 1, per_page: int = 20, category: str = "",
        min_rating: int | None = None, status: str = "",
    ) -> dict[str, Any]:
        start = (page - 1) * per_page
        end = start + per_page - 1
        query = (
            self._supabase.table("feedback")
            .select(_LIST_COLUMNS, count="exact")
            .order("created_at", desc=True)
        )
        if category:
            query = query.eq("category", category)
        if min_rating is not None:
            query = query.gte("rating", min_rating)
        if status:
            query = query.eq("status", status)
        result = query.range(start, end).execute()
        return {"data": result.data or [], "total_items": result.count or 0}

    def update_status(
        self, feedback_id: int, *, status: str, admin_note: str, handled_by: str,
    ) -> dict[str, Any] | None:
        """Hanya kolom tindak lanjut. Rating/kategori/komentar milik pengirim
        dan tidak pernah ditimpa dari sisi admin."""
        try:
            result = (
                self._supabase.table("feedback")
                .update({
                    "status": status,
                    "admin_note": admin_note or None,
                    "handled_by": handled_by,
                    "handled_at": datetime.now(timezone.utc).isoformat(),
                })
                .eq("id", feedback_id)
                .execute()
            )
            rows = result.data or []
            return rows[0] if rows else None
        except Exception as exc:
            print(f"[Feedback] Gagal update status feedback {feedback_id}: {exc}")
            return None

    def delete_feedback(self, feedback_id: int) -> bool:
        try:
            result = (
                self._supabase.table("feedback")
                .delete()
                .eq("id", feedback_id)
                .execute()
            )
            return bool(result.data)
        except Exception as exc:
            print(f"[Feedback] Gagal hapus feedback {feedback_id}: {exc}")
            return False

    def feedback_summary(self) -> dict[str, Any]:
        try:
            result = self._supabase.table("feedback").select("rating, category, status").execute()
            rows = result.data or []
        except Exception as exc:
            print(f"[Feedback] Gagal ambil ringkasan: {exc}")
            rows = []

        count = len(rows)
        avg_rating = round(sum(r.get("rating", 0) for r in rows) / count, 2) if count else None
        by_category: dict[str, int] = {}
        by_rating: dict[str, int] = {}
        for r in rows:
            cat = r.get("category") or "lainnya"
            by_category[cat] = by_category.get(cat, 0) + 1
            rating_key = str(r.get("rating"))
            by_rating[rating_key] = by_rating.get(rating_key, 0) + 1

        unhandled = sum(1 for r in rows if (r.get("status") or "baru") == "baru")
        return {
            "count": count, "avg_rating": avg_rating, "by_category": by_category,
            "by_rating": by_rating, "unhandled": unhandled,
        }
