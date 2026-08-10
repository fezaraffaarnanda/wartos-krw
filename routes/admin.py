"""
Blueprint: manajemen user (admin only) - list, create, delete, generate auth code.
"""

from flask import Blueprint, jsonify, request
from flask_login import current_user

from routes.auth import admin_required
from schemas.admin import CreateUsersPayload
from services.admin_service import AdminService
from services.relevance_feedback_service import RelevanceFeedbackService

admin_bp = Blueprint("admin", __name__)
_admin_service = AdminService()
_relevance_service = RelevanceFeedbackService()


@admin_bp.route("/api/admin/users", methods=["GET"])
@admin_required
def api_list_users():
    """Kembalikan daftar semua user beserta info kode reset aktif."""
    payload, status_code = _admin_service.list_users()
    return jsonify(payload), status_code


@admin_bp.route("/api/admin/users", methods=["POST"])
@admin_required
def api_create_user():
    """
    Buat user baru. Password di-generate otomatis dan dikembalikan sekali ke admin.
    User wajib ganti password saat pertama login.
    """
    body = request.get_json(silent=True) or {}
    data = CreateUsersPayload.from_body(body)

    payload, status_code = _admin_service.create_users(
        usernames=data.usernames,
        actor_username=current_user.username,
    )
    return jsonify(payload), status_code


@admin_bp.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
@admin_required
def api_delete_user(user_id: int):
    """Hapus user berdasarkan ID. Admin tidak dapat menghapus dirinya sendiri."""
    payload, status_code = _admin_service.delete_user(
        user_id=user_id,
        actor_user_id=current_user.id,
        actor_username=current_user.username,
    )
    return jsonify(payload), status_code


@admin_bp.route("/api/admin/users/<int:user_id>/auth-code", methods=["POST"])
@admin_required
def api_generate_auth_code(user_id: int):
    """
    Generate kode autentikasi 8 karakter untuk reset password.
    Kode lama dihapus, kode baru berlaku 1 jam.
    """
    payload, status_code = _admin_service.generate_user_auth_code(
        user_id=user_id,
        actor_username=current_user.username,
    )
    return jsonify(payload), status_code


# ── Feedback loop classifier relevance (tahap-1) ─────────────────────────────

@admin_bp.route("/api/admin/relevance/review-queue", methods=["GET"])
@admin_required
def api_relevance_review_queue():
    """Antrian review: mode=borderline|unlabeled|disagreement|all."""
    mode = (request.args.get("mode") or "borderline").strip()
    try:
        page = int(request.args.get("page", 1))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(request.args.get("per_page", 25))
    except (TypeError, ValueError):
        per_page = 25

    payload, status_code = _relevance_service.list_review_queue(
        mode=mode, page=page, per_page=per_page,
    )
    return jsonify(payload), status_code


@admin_bp.route("/api/admin/relevance/metrics", methods=["GET"])
@admin_required
def api_relevance_metrics():
    """Precision/recall classifier relevance vs label manusia."""
    payload, status_code = _relevance_service.metrics()
    return jsonify(payload), status_code


@admin_bp.route("/api/admin/relevance/disagreement-export", methods=["GET"])
@admin_required
def api_relevance_disagreement_export():
    """
    Ekspor kasus disagreement sebagai few-shot untuk iterasi prompt.
    Query param: ?limit=20 (default 20, max 50).
    """
    try:
        limit = min(int(request.args.get("limit", 20)), 50)
    except (TypeError, ValueError):
        limit = 20

    payload, status_code = _relevance_service.export_few_shot(limit)
    return jsonify(payload), status_code


@admin_bp.route("/api/admin/relevance/prompt", methods=["GET"])
@admin_required
def api_relevance_prompt():
    """Prompt relevance aktif + riwayat versi."""
    payload, status_code = _relevance_service.get_prompt_info()
    return jsonify(payload), status_code


@admin_bp.route("/api/admin/relevance/prompt-draft", methods=["POST"])
@admin_required
def api_relevance_prompt_draft():
    """Generate draft SYSTEM_PROMPT baru via LLM berdasarkan disagreement."""
    payload, status_code = _relevance_service.generate_prompt_draft()
    return jsonify(payload), status_code


@admin_bp.route("/api/admin/relevance/prompt-apply", methods=["POST"])
@admin_required
def api_relevance_prompt_apply():
    """
    Aktifkan prompt baru. Body: {draft_prompt, confirmation, notes?}.
    confirmation wajib persis "yes, update system prompt".
    """
    body = request.get_json(silent=True) or {}
    payload, status_code = _relevance_service.apply_prompt(
        draft_prompt=str(body.get("draft_prompt") or ""),
        confirmation=str(body.get("confirmation") or ""),
        username=current_user.username,
        notes=str(body.get("notes") or ""),
    )
    return jsonify(payload), status_code


@admin_bp.route("/api/admin/berita/<int:berita_id>/human-label", methods=["PATCH"])
@admin_required
def api_set_human_label(berita_id: int):
    """Override keputusan relevance oleh admin. Body: {is_relevant: bool}."""
    body = request.get_json(silent=True) or {}
    is_relevant = body.get("is_relevant")
    if not isinstance(is_relevant, bool):
        return jsonify({"status": "error", "message": "Field 'is_relevant' (bool) wajib diisi."}), 400

    payload, status_code = _relevance_service.set_human_label(
        berita_id,
        is_relevant=is_relevant,
        username=current_user.username,
    )
    return jsonify(payload), status_code
