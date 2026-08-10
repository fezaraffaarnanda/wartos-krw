"""
Blueprint: kontrol scraping - trigger, progress, backfill KBLI manual.
"""

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from config.extensions import limiter
from schemas.scraping import ScrapeTriggerPayload
from services.scraping_service import ScrapingService

scraping_bp = Blueprint("scraping", __name__)
_scraping_service = ScrapingService()


def _is_valid_api_key() -> bool:
    """Return True jika request membawa Authorization: Bearer <CRON_SECRET> yang valid."""
    return _scraping_service.is_valid_api_key(request.headers.get("Authorization", ""))


@scraping_bp.route("/api/scrape/progress", methods=["GET"])
@login_required
@limiter.exempt
def get_progress():
    return jsonify(_scraping_service.get_progress())


@scraping_bp.route("/api/sources", methods=["GET"])
@login_required
@limiter.exempt
def get_sources():
    """Daftar sumber berita aktif (key + label). Statis, tidak menyentuh DB."""
    payload, status_code = _scraping_service.list_sources()
    return jsonify(payload), status_code


@scraping_bp.route("/api/last-scrape", methods=["GET"])
@login_required
def get_last_scrape():
    """
    Kembalikan:
      - last_scrape : timestamp terakhir scraping berjalan (dari scrape_log)
      - new_count   : jumlah berita yang masuk hari ini (sejak 00:00 WIB)
    """
    payload, status_code = _scraping_service.get_last_scrape()
    return jsonify(payload), status_code


@scraping_bp.route("/api/scrape", methods=["POST"])
def start_scrape():
    """
    Dual auth:
      1. Session (dashboard) -> threaded, return langsung
      2. API key via header Authorization: Bearer <CRON_SECRET> -> synchronous
    """
    is_api_key = _is_valid_api_key()
    is_session = current_user.is_authenticated

    if not is_api_key and not is_session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    if is_session and not is_api_key and current_user.role != "admin":
        return jsonify(
            {
                "status": "error",
                "message": "Akses ditolak. Hanya admin yang dapat menjalankan scraping.",
            }
        ), 403

    body = request.get_json(silent=True) or {}
    payload = ScrapeTriggerPayload.from_body(body)

    result, status_code = _scraping_service.start_scrape(
        max_articles=payload.max_articles,
        is_api_key=is_api_key,
    )
    return jsonify(result), status_code


@scraping_bp.route("/api/admin/backfill-kbli", methods=["POST"])
@login_required
def api_backfill_kbli():
    """Trigger backfill prediksi KBLI untuk semua berita yang kbli-nya NULL. Admin only."""
    is_admin = current_user.role == "admin"
    payload, status_code = _scraping_service.trigger_kbli_backfill(is_admin=is_admin)
    return jsonify(payload), status_code
