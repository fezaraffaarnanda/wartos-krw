"""
Service layer untuk fitur feedback pengguna: tracking aktivitas, timing
prompt otomatis, submit, dismiss, dan rekap untuk admin.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from repositories.feedback import FeedbackRepository
from repositories.user_activity import UserActivityRepository

FEEDBACK_MILESTONE_EVENTS = 10
FEEDBACK_MILESTONE_DAYS = 3
DISMISS_SNOOZE_DAYS = 14
SUBMIT_SNOOZE_DAYS = 90


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class FeedbackService:
    """Use-case fitur feedback, lepas dari Flask route."""

    def __init__(
        self,
        feedback_repository: FeedbackRepository | None = None,
        activity_repository: UserActivityRepository | None = None,
    ):
        self._feedback = feedback_repository or FeedbackRepository()
        self._activity = activity_repository or UserActivityRepository()

    def track_event(self, *, user_id: int, event_type: str) -> tuple[dict[str, Any], int]:
        """Fail-soft: tracking tidak boleh menggagalkan aksi pengguna yang
        sesungguhnya (buka berita, kirim chat, dst). Kalau bump gagal,
        tetap balas ok dengan should_prompt dari state lama/kosong."""
        row = self._activity.bump(user_id=user_id, event_type=event_type)
        state = row or self._activity.get_state(user_id)
        should_prompt = self._should_prompt(state)
        return {
            "status": "ok",
            "event_count": (state or {}).get("event_count", 0),
            "should_prompt": should_prompt,
        }, 200

    def evaluate_prompt_state(self, *, user_id: int) -> dict[str, Any]:
        """Dipanggil dari GET /api/me -- satu PK lookup di tabel kecil,
        nol round-trip tambahan untuk halaman yang sudah memanggil /api/me."""
        state = self._activity.get_state(user_id)
        return {
            "should_prompt": self._should_prompt(state),
            "event_count": (state or {}).get("event_count", 0),
        }

    def _should_prompt(self, state: dict[str, Any] | None) -> bool:
        if not state:
            return False
        if state.get("feedback_submitted_at"):
            return False

        snoozed_until = _parse_iso(state.get("prompt_snoozed_until"))
        if snoozed_until and snoozed_until > datetime.now(timezone.utc):
            return False

        if int(state.get("event_count") or 0) < FEEDBACK_MILESTONE_EVENTS:
            return False

        first_login_at = _parse_iso(state.get("first_login_at"))
        if first_login_at is None:
            return False
        milestone_cutoff = datetime.now(timezone.utc) - timedelta(days=FEEDBACK_MILESTONE_DAYS)
        return first_login_at <= milestone_cutoff

    def submit_feedback(
        self,
        *,
        user_id: int,
        username: str,
        role: str,
        rating: int,
        category: str,
        comment: str,
        page_path: str,
        trigger_source: str,
    ) -> tuple[dict[str, Any], int]:
        state = self._activity.get_state(user_id)
        event_count = int((state or {}).get("event_count") or 0)

        row = self._feedback.insert_feedback(
            user_id=user_id, username=username, role=role, rating=rating, category=category,
            comment=comment, page_path=page_path, event_count_at_submit=event_count,
            trigger_source=trigger_source,
        )
        if not row:
            return {"status": "error", "message": "Gagal menyimpan masukan."}, 500

        self._activity.mark_submitted(user_id=user_id, snooze_days=SUBMIT_SNOOZE_DAYS)
        return {"status": "ok", "message": "Terima kasih atas masukannya."}, 200

    def dismiss_prompt(self, *, user_id: int) -> tuple[dict[str, Any], int]:
        row = self._activity.snooze(user_id=user_id, days=DISMISS_SNOOZE_DAYS)
        if not row:
            return {"status": "ok", "snoozed_until": None}, 200
        return {"status": "ok", "snoozed_until": row.get("prompt_snoozed_until")}, 200

    def list_feedback(
        self, *, page: int = 1, per_page: int = 20, category: str = "",
        min_rating: int | None = None, status: str = "",
    ) -> tuple[dict[str, Any], int]:
        result = self._feedback.list_feedback(
            page=page, per_page=per_page, category=category, min_rating=min_rating, status=status,
        )
        total_items = result["total_items"]
        summary = self._feedback.feedback_summary()
        return {
            "status": "ok",
            "page": page,
            "per_page": per_page,
            "total_items": total_items,
            "total_pages": max(1, -(-total_items // per_page)),
            "data": result["data"],
            "summary": summary,
        }, 200

    def update_feedback_status(
        self, feedback_id: int, *, status: str, admin_note: str, username: str,
    ) -> tuple[dict[str, Any], int]:
        if feedback_id <= 0:
            return {"status": "error", "message": "ID tidak valid."}, 400
        row = self._feedback.update_status(
            feedback_id, status=status, admin_note=admin_note, handled_by=username,
        )
        if not row:
            return {"status": "error", "message": "Masukan tidak ditemukan."}, 404
        return {"status": "ok", "data": row}, 200

    def delete_feedback(self, feedback_id: int) -> tuple[dict[str, Any], int]:
        if feedback_id <= 0:
            return {"status": "error", "message": "ID tidak valid."}, 400
        if not self._feedback.delete_feedback(feedback_id):
            return {"status": "error", "message": "Masukan tidak ditemukan."}, 404
        return {"status": "ok", "message": "Masukan dihapus."}, 200
