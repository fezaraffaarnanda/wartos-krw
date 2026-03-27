"""Blueprint statistik resmi BPS untuk dashboard."""

from flask import Blueprint, jsonify, request
from flask_login import login_required

from config.extensions import limiter
from services.official_statistics_service import get_official_statistics_dashboard_payload

official_statistics_bp = Blueprint("official_statistics", __name__)


@official_statistics_bp.route("/api/official-statistics", methods=["GET"])
@login_required
@limiter.limit("120 per hour")
def get_official_statistics():
    year_raw = str(request.args.get("year", "")).strip()
    force_refresh = request.args.get("refresh", "") == "1"

    if year_raw and not year_raw.isdigit():
        return jsonify({"status": "error", "message": "Parameter tahun tidak valid."}), 400

    try:
        payload = get_official_statistics_dashboard_payload(
            int(year_raw) if year_raw else None,
            force_refresh=force_refresh,
        )
        return jsonify(payload)
    except Exception as exc:
        print(f"[BPS] Gagal menyajikan statistik resmi: {exc}")
        return jsonify({"status": "error", "message": "Gagal mengambil statistik resmi BPS."}), 500
