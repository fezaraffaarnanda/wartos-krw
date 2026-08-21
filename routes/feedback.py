"""
Blueprint: fitur feedback pengguna - tracking aktivitas, submit, dismiss,
dan rekap untuk admin.
"""

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from config.extensions import limiter
from routes.auth import admin_required
from schemas.feedback import (
    ActivityTrackPayload,
    FeedbackListQuery,
    FeedbackStatusPayload,
    FeedbackSubmitPayload,
)
from services.feedback_service import FeedbackService

feedback_bp = Blueprint("feedback", __name__)
_feedback_service = FeedbackService()


@feedback_bp.route("/api/activity/track", methods=["POST"])
@login_required
@limiter.limit("600 per hour")
def api_activity_track():
    """Catat satu event pemakaian fitur, dipakai memicu prompt feedback.
    Body: {event_type}. event_type WAJIB dari allowlist."""
    body = request.get_json(silent=True) or {}
    payload_in = ActivityTrackPayload.from_body(body)
    if payload_in is None:
        return jsonify({"status": "error", "message": "event_type tidak dikenali."}), 400

    payload, status_code = _feedback_service.track_event(
        user_id=int(current_user.id), event_type=payload_in.event_type,
    )
    return jsonify(payload), status_code


@feedback_bp.route("/api/feedback", methods=["POST"])
@login_required
@limiter.limit("10 per hour")
def api_feedback_submit():
    """Kirim masukan. Body: {rating, category, comment?, page_path?, trigger_source?}."""
    body = request.get_json(silent=True) or {}
    payload_in = FeedbackSubmitPayload.from_body(body)
    if payload_in is None:
        return jsonify({"status": "error", "message": "Rating (1-5) dan kategori wajib diisi."}), 400

    payload, status_code = _feedback_service.submit_feedback(
        user_id=int(current_user.id),
        username=current_user.username,
        role=current_user.role,
        rating=payload_in.rating,
        category=payload_in.category,
        comment=payload_in.comment,
        page_path=payload_in.page_path,
        trigger_source=payload_in.trigger_source,
    )
    return jsonify(payload), status_code


@feedback_bp.route("/api/feedback/dismiss", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def api_feedback_dismiss():
    """Tunda prompt otomatis 14 hari. Tombol sidebar tidak memanggil ini."""
    payload, status_code = _feedback_service.dismiss_prompt(user_id=int(current_user.id))
    return jsonify(payload), status_code


@feedback_bp.route("/api/admin/feedback", methods=["GET"])
@admin_required
def api_admin_feedback_list():
    """Rekap feedback untuk admin: daftar + ringkasan (rata-rata rating, per kategori)."""
    q = FeedbackListQuery.from_request_args(request.args)
    payload, status_code = _feedback_service.list_feedback(
        page=q.page, per_page=q.per_page, category=q.category,
        min_rating=q.min_rating, status=q.status,
    )
    return jsonify(payload), status_code


@feedback_bp.route("/api/admin/feedback/<int:feedback_id>", methods=["PATCH"])
@admin_required
@limiter.limit("300 per hour")
def api_admin_feedback_update(feedback_id: int):
    """Tandai tindak lanjut satu masukan. Body: {status, admin_note?}.

    Sengaja tidak menerima rating/kategori/komentar: isi masukan adalah
    kesaksian pengirim dan tidak boleh ditulis ulang oleh admin."""
    body = request.get_json(silent=True) or {}
    payload_in = FeedbackStatusPayload.from_body(body)
    if payload_in is None:
        return jsonify({"status": "error", "message": "Status tidak dikenali."}), 400

    payload, status_code = _feedback_service.update_feedback_status(
        feedback_id,
        status=payload_in.status,
        admin_note=payload_in.admin_note,
        username=current_user.username,
    )
    return jsonify(payload), status_code


@feedback_bp.route("/api/admin/feedback/<int:feedback_id>", methods=["DELETE"])
@admin_required
@limiter.limit("100 per hour")
def api_admin_feedback_delete(feedback_id: int):
    """Hapus satu masukan (spam / salah kirim). Permanen."""
    payload, status_code = _feedback_service.delete_feedback(feedback_id)
    return jsonify(payload), status_code
