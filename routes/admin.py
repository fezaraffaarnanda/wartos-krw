"""
Blueprint: manajemen user (admin only) - list, create, delete, generate auth code.
Plus audit classifier relevance (tahap-1): antrian review, label manusia,
re-classify, sampel audit, metrik, dan siklus hidup prompt.
Plus pengaturan provider LLM & usage log.
"""

from flask import Blueprint, jsonify, request
from flask_login import current_user

from config.extensions import limiter
from routes.auth import admin_required
from schemas.admin import CreateUsersPayload
from schemas.relevance import (
    AuditSamplePayload,
    BulkLabelPayload,
    FewShotExportQuery,
    HumanLabelPayload,
    PromptApplyPayload,
    PromptDraftPayload,
    PromptEvalPayload,
    PromptRollbackPayload,
    ReclassifyBulkPayload,
    RelevanceMetricsQuery,
    RelevanceQueueQuery,
)
from services.admin_service import AdminService
from services.llm_settings_service import LlmSettingsService
from services.relevance_feedback_service import RelevanceFeedbackService
from services.relevance_prompt_service import RelevancePromptService

admin_bp = Blueprint("admin", __name__)
_admin_service = AdminService()
_relevance_service = RelevanceFeedbackService()
_prompt_service = RelevancePromptService()
_llm_settings_service = LlmSettingsService()


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


# ── Audit classifier relevance (tahap-1) — antrian & label ───────────────────

@admin_bp.route("/api/admin/relevance/review-queue", methods=["GET"])
@admin_required
def api_relevance_review_queue():
    """Antrian review: mode=uncertainty|audit|failed|labeled|disagreement|all."""
    q = RelevanceQueueQuery.from_request_args(request.args)
    payload, status_code = _relevance_service.list_review_queue(
        mode=q.mode, page=q.page, per_page=q.per_page,
        search=q.search, source=q.source, score_min=q.score_min, score_max=q.score_max,
    )
    return jsonify(payload), status_code


@admin_bp.route("/api/admin/relevance/item/<int:berita_id>", methods=["GET"])
@admin_required
@limiter.limit("900 per hour")
def api_relevance_item(berita_id: int):
    """Detail satu item (termasuk content penuh) untuk panel review.

    Rate limit tinggi disengaja: prefetch 2 item berikutnya berjalan tiap
    admin berpindah item saat sprint labeling.
    """
    payload, status_code = _relevance_service.get_review_item(berita_id)
    return jsonify(payload), status_code


@admin_bp.route("/api/admin/berita/<int:berita_id>/human-label", methods=["PATCH"])
@admin_required
@limiter.limit("900 per hour")
def api_set_human_label(berita_id: int):
    """Override keputusan relevance oleh admin.

    Rate limit tinggi disengaja: default global 300/jam akan menembus di
    sprint labeling keyboard-driven (satu request per keystroke).
    """
    body = request.get_json(silent=True) or {}
    payload_in = HumanLabelPayload.from_body(body)
    payload, status_code = _relevance_service.set_human_label(
        berita_id,
        is_relevant=payload_in.is_relevant,
        username=current_user.username,
        label_source=payload_in.label_source,
        note=payload_in.note,
    )
    return jsonify(payload), status_code


@admin_bp.route("/api/admin/berita/<int:berita_id>/human-label", methods=["DELETE"])
@admin_required
@limiter.limit("300 per hour")
def api_clear_human_label(berita_id: int):
    """Hapus label manusia pada satu item (bukan undo aksi terakhir -- lihat /relevance/undo)."""
    payload, status_code = _relevance_service.clear_human_label(berita_id, username=current_user.username)
    return jsonify(payload), status_code


@admin_bp.route("/api/admin/relevance/undo", methods=["POST"])
@admin_required
@limiter.limit("300 per hour")
def api_relevance_undo():
    """Batalkan label terakhir milik admin yang sedang login (tombol pintasan 'u').

    Server-side (relevance_label_events), jadi tetap bekerja setelah reload
    halaman -- bukan cuma stack di memori browser.
    """
    payload, status_code = _relevance_service.undo_last_label(username=current_user.username)
    return jsonify(payload), status_code


@admin_bp.route("/api/admin/relevance/bulk-label", methods=["POST"])
@admin_required
@limiter.limit("60 per hour")
def api_relevance_bulk_label():
    """Label banyak berita sekaligus dengan keputusan yang sama. Maks 50 ID per panggilan."""
    body = request.get_json(silent=True) or {}
    payload_in = BulkLabelPayload.from_body(body)
    payload, status_code = _relevance_service.bulk_set_human_label(
        berita_ids=payload_in.berita_ids,
        is_relevant=payload_in.is_relevant,
        username=current_user.username,
        label_source=payload_in.label_source,
    )
    return jsonify(payload), status_code


# ── Re-classify ───────────────────────────────────────────────────────────────

@admin_bp.route("/api/admin/berita/<int:berita_id>/reclassify", methods=["POST"])
@admin_required
@limiter.limit("120 per hour")
def api_relevance_reclassify_one(berita_id: int):
    """Klasifikasi ulang satu artikel, mengabaikan batas percobaan otomatis backfill."""
    payload, status_code = _relevance_service.reclassify_one(berita_id)
    return jsonify(payload), status_code


@admin_bp.route("/api/admin/relevance/reclassify-bulk", methods=["POST"])
@admin_required
@limiter.limit("20 per hour")
def api_relevance_reclassify_bulk():
    """Klasifikasi ulang banyak artikel. Tanpa berita_ids -> ambil dari antrian
    'Gagal Diklasifikasi' (maks `limit`, default 25 -- batas timeout serverless)."""
    body = request.get_json(silent=True) or {}
    payload_in = ReclassifyBulkPayload.from_body(body)
    payload, status_code = _relevance_service.reclassify_bulk(
        berita_ids=payload_in.berita_ids or None, limit=payload_in.limit,
    )
    return jsonify(payload), status_code


# ── Sampel audit acak berstrata ───────────────────────────────────────────────

@admin_bp.route("/api/admin/relevance/audit-sample", methods=["POST"])
@admin_required
@limiter.limit("10 per hour")
def api_relevance_draw_audit_sample():
    """Tarik sampel acak berstrata baru untuk audit tak bias."""
    body = request.get_json(silent=True) or {}
    payload_in = AuditSamplePayload.from_body(body)
    payload, status_code = _relevance_service.draw_audit_sample(
        per_band=payload_in.per_band, username=current_user.username,
    )
    return jsonify(payload), status_code


@admin_bp.route("/api/admin/relevance/audit-sample", methods=["GET"])
@admin_required
def api_relevance_audit_sample_status():
    """Progres batch sampel audit yang sedang terbuka (kalau ada)."""
    payload, status_code = _relevance_service.audit_sample_status()
    return jsonify(payload), status_code


# ── Metrik & few-shot export ──────────────────────────────────────────────────

@admin_bp.route("/api/admin/relevance/metrics", methods=["GET"])
@admin_required
def api_relevance_metrics():
    """Precision/recall classifier relevance: blok sample (semua label, bias)
    + audit (berbobot strata, tak bias bila label audit cukup) + per versi prompt."""
    q = RelevanceMetricsQuery.from_request_args(request.args)
    payload, status_code = _relevance_service.metrics(prompt_version=q.prompt_version)
    return jsonify(payload), status_code


@admin_bp.route("/api/admin/relevance/few-shot-export", methods=["GET"])
@admin_required
@limiter.limit("30 per hour")
def api_relevance_few_shot_export():
    """Ekspor menu kurasi few-shot dari SEMUA label (koreksi + konfirmasi)."""
    q = FewShotExportQuery.from_request_args(request.args)
    payload, status_code = _relevance_service.export_few_shot(q.limit)
    return jsonify(payload), status_code


# ── Siklus hidup prompt ───────────────────────────────────────────────────────

@admin_bp.route("/api/admin/relevance/prompt", methods=["GET"])
@admin_required
def api_relevance_prompt():
    """Prompt relevance aktif + riwayat versi."""
    payload, status_code = _prompt_service.get_prompt_info()
    return jsonify(payload), status_code


@admin_bp.route("/api/admin/relevance/prompt-draft", methods=["POST"])
@admin_required
@limiter.limit("10 per hour")
def api_relevance_prompt_draft():
    """Generate draft SYSTEM_PROMPT baru via LLM dari label manusia.

    400 hanya bila total label < 12 -- BUKAN bila disagreement/koreksi == 0
    (itu bug versi lama: dengan 0 disagreement panggilan ini selalu 400).
    """
    body = request.get_json(silent=True) or {}
    payload_in = PromptDraftPayload.from_body(body)
    payload, status_code = _prompt_service.generate_draft(limit=payload_in.limit)
    return jsonify(payload), status_code


@admin_bp.route("/api/admin/relevance/prompt-eval", methods=["POST"])
@admin_required
@limiter.limit("5 per hour")
def api_relevance_prompt_eval():
    """Dry-run: skor draft DAN prompt aktif pada golden set yang sama, tanpa mengubah apa pun."""
    body = request.get_json(silent=True) or {}
    payload_in = PromptEvalPayload.from_body(body)
    payload, status_code = _prompt_service.evaluate_draft(
        draft_prompt=payload_in.draft_prompt, sample_size=payload_in.sample_size,
    )
    return jsonify(payload), status_code


@admin_bp.route("/api/admin/relevance/prompt-apply", methods=["POST"])
@admin_required
@limiter.limit("10 per hour")
def api_relevance_prompt_apply():
    """Aktifkan prompt baru. confirmation wajib persis "yes, update system prompt"."""
    body = request.get_json(silent=True) or {}
    payload_in = PromptApplyPayload.from_body(body)
    payload, status_code = _prompt_service.apply_prompt(
        draft_prompt=payload_in.draft_prompt,
        confirmation=payload_in.confirmation,
        username=current_user.username,
        notes=payload_in.notes,
        eval_result=payload_in.eval_result,
    )
    return jsonify(payload), status_code


@admin_bp.route("/api/admin/relevance/prompt-rollback", methods=["POST"])
@admin_required
@limiter.limit("10 per hour")
def api_relevance_prompt_rollback():
    """Rollback ke versi prompt lama. confirmation wajib persis "yes, update system prompt"."""
    body = request.get_json(silent=True) or {}
    payload_in = PromptRollbackPayload.from_body(body)
    payload, status_code = _prompt_service.rollback_prompt(
        version=payload_in.version, confirmation=payload_in.confirmation, username=current_user.username,
    )
    return jsonify(payload), status_code


# ── Pengaturan provider LLM (Gemini/DeepSeek) & usage log ────────────────────

@admin_bp.route("/api/admin/llm/provider", methods=["GET"])
@admin_required
def api_llm_provider_get():
    """Provider LLM default aktif + ketersediaan API key tiap provider."""
    payload, status_code = _llm_settings_service.get_provider_info()
    return jsonify(payload), status_code


@admin_bp.route("/api/admin/llm/provider", methods=["POST"])
@admin_required
def api_llm_provider_set():
    """Ganti provider LLM default. Body: {provider: 'deepseek'|'gemini'}."""
    body = request.get_json(silent=True) or {}
    payload, status_code = _llm_settings_service.set_provider(
        str(body.get("provider") or ""),
        actor_username=current_user.username,
    )
    return jsonify(payload), status_code


@admin_bp.route("/api/admin/llm/usage", methods=["GET"])
@admin_required
def api_llm_usage():
    """Ringkasan token usage per fitur & provider. Query param: ?days=30 (default 30, max 90)."""
    try:
        days = min(max(int(request.args.get("days", 30)), 1), 90)
    except (TypeError, ValueError):
        days = 30

    payload, status_code = _llm_settings_service.usage_summary(days)
    return jsonify(payload), status_code
