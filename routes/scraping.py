"""
Blueprint: kontrol scraping — trigger, progress, backfill KBLI manual.
"""

import os
import threading

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from services.article_pipeline import (
    _run_kbli_backfill,
    _scrape_sync,
    _scrape_worker,
)
from state.scraping import (
    _scrape_progress,
    _scrape_overall,
    _scraping_lock,
    _reset_progress,
)
from config.extensions import limiter

scraping_bp = Blueprint("scraping", __name__)


def _is_valid_api_key() -> bool:
    """Return True jika request membawa header Authorization: Bearer <CRON_SECRET> yang valid."""
    cron_secret = os.getenv("CRON_SECRET", "")
    if not cron_secret:
        return False
    return request.headers.get("Authorization", "") == f"Bearer {cron_secret}"


@scraping_bp.route("/api/scrape/progress", methods=["GET"])
@login_required
@limiter.exempt
def get_progress():
    return jsonify({"progress": _scrape_progress, "overall": _scrape_overall})


@scraping_bp.route("/api/last-scrape", methods=["GET"])
@login_required
def get_last_scrape():
    """
    Kembalikan:
      - last_scrape : timestamp terakhir scraping berjalan (dari scrape_log)
      - new_count   : jumlah berita yang masuk hari ini (sejak 00:00 WIB)
    """
    from repositories.scrape_log import _fetch_last_scrape_timestamp, _count_todays_articles
    try:
        last_scrape = _fetch_last_scrape_timestamp()
        new_count   = _count_todays_articles()
        return jsonify({"status": "ok", "last_scrape": last_scrape, "new_count": new_count})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@scraping_bp.route("/api/scrape", methods=["POST"])
def start_scrape():
    """
    Dual auth:
      1. Session (dashboard) → threaded, return langsung
      2. API key via header Authorization: Bearer <CRON_SECRET> → synchronous
    """
    is_api_key = _is_valid_api_key()
    is_session = current_user.is_authenticated

    if not is_api_key and not is_session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    if is_session and not is_api_key and current_user.role != "admin":
        return jsonify({"status": "error", "message": "Akses ditolak. Hanya admin yang dapat menjalankan scraping."}), 403

    body         = request.get_json(silent=True) or {}
    max_articles = max(1, min(int(body.get("max_articles", 150)), 999))

    if is_api_key:
        print(f"[SCRAPE] Dipanggil via API key — mode synchronous, maks {max_articles} artikel")
        result = _scrape_sync(max_articles)
        return jsonify(result), 200 if result.get("status") == "ok" else 500

    if not _scraping_lock.acquire(blocking=False):
        return jsonify({"status": "error", "message": "Scraping sedang berjalan, tunggu hingga selesai."}), 409

    _reset_progress()
    threading.Thread(target=_scrape_worker, args=(max_articles,), daemon=True).start()
    return jsonify({"status": "started", "max_articles": max_articles})


@scraping_bp.route("/api/admin/backfill-kbli", methods=["POST"])
@login_required
def api_backfill_kbli():
    """Trigger backfill prediksi KBLI untuk semua berita yang kbli-nya NULL. Admin only."""
    if current_user.role != "admin":
        return jsonify({"status": "error", "message": "Akses ditolak. Hanya admin."}), 403

    from services.article_pipeline import _classifiers
    if _classifiers["kbli_predictor"] is None:
        return jsonify({
            "status":  "error",
            "message": "KBLI Classifier tidak tersedia. Periksa GEMINI_API_KEY dan koneksi Supabase.",
        }), 503

    threading.Thread(
        target=_run_kbli_backfill,
        daemon=True,
        name="kbli-backfill-manual",
    ).start()
    return jsonify({"status": "started", "message": "Backfill KBLI dimulai di background."})
