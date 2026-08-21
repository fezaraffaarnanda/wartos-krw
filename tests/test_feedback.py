from datetime import datetime, timedelta, timezone

from schemas.feedback import (
    ActivityTrackPayload,
    FeedbackListQuery,
    FeedbackStatusPayload,
    FeedbackSubmitPayload,
)
from services.feedback_service import FeedbackService


# ── schemas ──────────────────────────────────────────────────────────────

def test_activity_track_rejects_unknown_event_type():
    assert ActivityTrackPayload.from_body({"event_type": "bogus"}) is None


def test_activity_track_accepts_known_event_type():
    p = ActivityTrackPayload.from_body({"event_type": "berita_detail_open"})
    assert p.event_type == "berita_detail_open"


def test_feedback_submit_rejects_out_of_range_rating():
    """rating WAJIB ditolak kalau di luar 1-5, bukan diclamp -- rating adalah
    domain tetap (bintang), beda dari page/per_page yang wajar diclamp."""
    assert FeedbackSubmitPayload.from_body({"rating": 9, "category": "berita"}) is None
    assert FeedbackSubmitPayload.from_body({"rating": 0, "category": "berita"}) is None


def test_feedback_submit_rejects_missing_category():
    assert FeedbackSubmitPayload.from_body({"rating": 5, "category": "nonsense"}) is None


def test_feedback_submit_accepts_valid_payload_and_trims_comment():
    p = FeedbackSubmitPayload.from_body({
        "rating": "4", "category": "ai_chat", "comment": "  bagus  ", "trigger_source": "auto_prompt",
    })
    assert p.rating == 4
    assert p.comment == "bagus"
    assert p.trigger_source == "auto_prompt"


def test_feedback_submit_falls_back_bad_trigger_source():
    p = FeedbackSubmitPayload.from_body({"rating": 3, "category": "berita", "trigger_source": "bogus"})
    assert p.trigger_source == "sidebar"


def test_feedback_list_query_falls_back_bad_category_and_min_rating():
    q = FeedbackListQuery.from_request_args({"category": "bogus", "min_rating": "99", "page": "-1"})
    assert q.category == ""
    assert q.min_rating is None
    assert q.page == 1


# ── service: _should_prompt trigger formula ─────────────────────────────

class _FakeActivityRepo:
    def __init__(self, state):
        self._state = state

    def bump(self, *, user_id, event_type):
        return self._state

    def get_state(self, user_id):
        return self._state

    def snooze(self, *, user_id, days):
        return self._state

    def mark_submitted(self, *, user_id, snooze_days=90):
        return self._state


class _FakeFeedbackRepo:
    def insert_feedback(self, **_kwargs):
        return {"id": 1}

    def list_feedback(self, **_kwargs):
        return {"data": [], "total_items": 0}

    def feedback_summary(self):
        return {"count": 0, "avg_rating": None, "by_category": {}, "by_rating": {}}


def _old_login(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def test_should_prompt_false_when_no_state():
    svc = FeedbackService(_FakeFeedbackRepo(), _FakeActivityRepo(None))
    assert svc.evaluate_prompt_state(user_id=1)["should_prompt"] is False


def test_should_prompt_false_under_event_threshold():
    state = {"event_count": 9, "first_login_at": _old_login(10), "feedback_submitted_at": None, "prompt_snoozed_until": None}
    svc = FeedbackService(_FakeFeedbackRepo(), _FakeActivityRepo(state))
    assert svc.evaluate_prompt_state(user_id=1)["should_prompt"] is False


def test_should_prompt_false_when_account_too_new():
    state = {"event_count": 20, "first_login_at": _old_login(1), "feedback_submitted_at": None, "prompt_snoozed_until": None}
    svc = FeedbackService(_FakeFeedbackRepo(), _FakeActivityRepo(state))
    assert svc.evaluate_prompt_state(user_id=1)["should_prompt"] is False


def test_should_prompt_false_when_already_submitted():
    state = {"event_count": 20, "first_login_at": _old_login(10), "feedback_submitted_at": _old_login(1), "prompt_snoozed_until": None}
    svc = FeedbackService(_FakeFeedbackRepo(), _FakeActivityRepo(state))
    assert svc.evaluate_prompt_state(user_id=1)["should_prompt"] is False


def test_should_prompt_false_when_snoozed():
    state = {
        "event_count": 20, "first_login_at": _old_login(10), "feedback_submitted_at": None,
        "prompt_snoozed_until": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
    }
    svc = FeedbackService(_FakeFeedbackRepo(), _FakeActivityRepo(state))
    assert svc.evaluate_prompt_state(user_id=1)["should_prompt"] is False


def test_should_prompt_true_when_all_conditions_met():
    state = {"event_count": 10, "first_login_at": _old_login(4), "feedback_submitted_at": None, "prompt_snoozed_until": None}
    svc = FeedbackService(_FakeFeedbackRepo(), _FakeActivityRepo(state))
    result = svc.evaluate_prompt_state(user_id=1)
    assert result["should_prompt"] is True
    assert result["event_count"] == 10


def test_should_prompt_true_when_snooze_already_expired():
    state = {
        "event_count": 15, "first_login_at": _old_login(10), "feedback_submitted_at": None,
        "prompt_snoozed_until": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
    }
    svc = FeedbackService(_FakeFeedbackRepo(), _FakeActivityRepo(state))
    assert svc.evaluate_prompt_state(user_id=1)["should_prompt"] is True


def test_submit_feedback_returns_error_when_insert_fails():
    class _FailingRepo(_FakeFeedbackRepo):
        def insert_feedback(self, **_kwargs):
            return None

    svc = FeedbackService(_FailingRepo(), _FakeActivityRepo({"event_count": 3}))
    payload, status = svc.submit_feedback(
        user_id=1, username="x", role="user", rating=5, category="berita",
        comment="", page_path="", trigger_source="sidebar",
    )
    assert status == 500
    assert payload["status"] == "error"


def test_submit_feedback_ok_on_success():
    svc = FeedbackService(_FakeFeedbackRepo(), _FakeActivityRepo({"event_count": 3}))
    payload, status = svc.submit_feedback(
        user_id=1, username="x", role="user", rating=5, category="berita",
        comment="", page_path="", trigger_source="sidebar",
    )
    assert status == 200
    assert payload["status"] == "ok"


# ── tindak lanjut admin ──────────────────────────────────────────────────

def test_status_payload_rejects_unknown_status():
    assert FeedbackStatusPayload.from_body({"status": "selesai"}) is None
    assert FeedbackStatusPayload.from_body({}) is None


def test_status_payload_accepts_known_status_and_trims_note():
    p = FeedbackStatusPayload.from_body({"status": "Ditindaklanjuti", "admin_note": "  sudah  "})
    assert p.status == "ditindaklanjuti"
    assert p.admin_note == "sudah"


def test_status_payload_ignores_user_owned_fields():
    """Isi masukan milik pengirim: rating/kategori/komentar tidak boleh ikut
    tertulis lewat endpoint admin, sekalipun dikirim di body."""
    p = FeedbackStatusPayload.from_body({
        "status": "dibaca", "rating": 1, "category": "berita", "comment": "diganti admin",
    })
    assert not hasattr(p, "rating")
    assert not hasattr(p, "comment")
    assert p.model_dump() == {"status": "dibaca", "admin_note": ""}


def test_list_query_accepts_status_filter_and_drops_bogus_one():
    assert FeedbackListQuery.from_request_args({"status": "baru"}).status == "baru"
    assert FeedbackListQuery.from_request_args({"status": "ngawur"}).status == ""


class _FakeAdminFeedbackRepo:
    def __init__(self, updated=None, deleted=True):
        self.updated = updated
        self.deleted = deleted
        self.update_args = None
        self.deleted_id = None

    def update_status(self, feedback_id, *, status, admin_note, handled_by):
        self.update_args = (feedback_id, status, admin_note, handled_by)
        return self.updated

    def delete_feedback(self, feedback_id):
        self.deleted_id = feedback_id
        return self.deleted


def test_update_status_records_who_handled_it():
    repo = _FakeAdminFeedbackRepo(updated={"id": 3, "status": "dibaca"})
    svc = FeedbackService(feedback_repository=repo, activity_repository=object())
    payload, status = svc.update_feedback_status(3, status="dibaca", admin_note="cek", username="admin")

    assert status == 200
    assert repo.update_args == (3, "dibaca", "cek", "admin")
    assert payload["data"]["status"] == "dibaca"


def test_update_status_on_missing_row_is_not_found():
    svc = FeedbackService(feedback_repository=_FakeAdminFeedbackRepo(updated=None), activity_repository=object())
    _payload, status = svc.update_feedback_status(99, status="baru", admin_note="", username="admin")
    assert status == 404


def test_delete_feedback_reports_missing_row():
    svc = FeedbackService(feedback_repository=_FakeAdminFeedbackRepo(deleted=False), activity_repository=object())
    _payload, status = svc.delete_feedback(99)
    assert status == 404


def test_delete_feedback_rejects_invalid_id_before_touching_repo():
    repo = _FakeAdminFeedbackRepo()
    svc = FeedbackService(feedback_repository=repo, activity_repository=object())
    _payload, status = svc.delete_feedback(0)
    assert status == 400
    assert repo.deleted_id is None
