"""
Blueprint: API data berita + data dashboard overview.
"""

from flask import Blueprint, jsonify, request
from flask_login import login_required

from schemas.berita import BeritaArchivePayload, BeritaClassificationPayload, BeritaFilterQuery
from services.berita_service import BeritaService

berita_bp = Blueprint("berita", __name__)
_berita_service = BeritaService()


@berita_bp.route("/api/berita", methods=["GET"])
@login_required
def get_berita():
    """
    Kembalikan daftar berita ter-pagination TANPA kolom content.
    Query params:
      - search, date_from, date_to
      - page (default 1)
      - per_page (default 15, max 100)
      - sort_by: date/date_parsed/title/source/tags/created_at
      - sort_dir: asc/desc
    """
    try:
        query = BeritaFilterQuery.from_request_args(request.args)
        return jsonify(_berita_service.list_berita(query))
    except Exception:
        return jsonify({"status": "error", "message": "Gagal mengambil data."}), 500


@berita_bp.route("/api/dashboard/overview/summary", methods=["GET"])
@login_required
def get_dashboard_overview_summary():
    """Ringkasan statistik dashboard untuk 30 hari terakhir (ringan, tanpa tabel lengkap)."""
    try:
        return jsonify(_berita_service.get_dashboard_overview_summary())
    except Exception:
        return jsonify({"status": "error", "message": "Gagal mengambil ringkasan dashboard."}), 500


@berita_bp.route("/api/berita/export", methods=["GET"])
@login_required
def export_berita():
    """Endpoint khusus download Excel (termasuk kolom content)."""
    try:
        query = BeritaFilterQuery.from_request_args(request.args)
        return jsonify(_berita_service.export_berita(query))
    except Exception:
        return jsonify({"status": "error", "message": "Gagal mengekspor data."}), 500


@berita_bp.route("/api/berita/years", methods=["GET"])
@login_required
def get_berita_years():
    """Kembalikan list tahun unik yang ada di kolom date_parsed, urut DESC."""
    try:
        return jsonify(_berita_service.get_berita_years())
    except Exception:
        return jsonify({"status": "error", "message": "Gagal mengambil daftar tahun."}), 500


@berita_bp.route("/api/dashboard/data/filter-options", methods=["GET"])
@login_required
def get_dashboard_data_filter_options():
    """Ambil opsi filter KBLI dan Aktivitas dari data yang tersedia."""
    try:
        return jsonify(_berita_service.get_dashboard_data_filter_options())
    except Exception:
        return jsonify({"status": "error", "message": "Gagal mengambil opsi filter."}), 500


@berita_bp.route("/api/berita/<int:berita_id>", methods=["GET"])
@login_required
def get_berita_by_id(berita_id: int):
    if berita_id <= 0:
        return jsonify({"status": "error", "message": "ID tidak valid."}), 400

    try:
        row = _berita_service.get_berita_by_id(berita_id)
        if not row:
            return jsonify({"status": "error", "message": "Berita tidak ditemukan."}), 404
        return jsonify({"status": "ok", "data": row})
    except Exception:
        return jsonify({"status": "error", "message": "Berita tidak ditemukan."}), 404


@berita_bp.route("/api/berita/<int:berita_id>/archive", methods=["PATCH"])
@login_required
def update_berita_archive_status(berita_id: int):
    body = request.get_json(silent=True) or {}
    payload = BeritaArchivePayload.from_body(body)

    try:
        response, status_code = _berita_service.update_archive_status(
            berita_id,
            is_archived=payload.is_archived,
        )
        return jsonify(response), status_code
    except Exception as exc:
        print(f"[BERITA] Error endpoint archive berita {berita_id}: {exc}")
        return jsonify({"status": "error", "message": "Gagal memperbarui status arsip."}), 500


@berita_bp.route("/api/berita/<int:berita_id>/classification", methods=["PATCH"])
@login_required
def update_berita_classification(berita_id: int):
    body = request.get_json(silent=True) or {}
    payload = BeritaClassificationPayload.from_body(body)

    try:
        response, status_code = _berita_service.update_classification(
            berita_id,
            kbli_code=payload.kbli_code,
            aktivitas_code=payload.aktivitas_code,
            pdrb_pengeluaran_code=payload.pdrb_pengeluaran_code,
        )
        return jsonify(response), status_code
    except Exception as exc:
        print(f"[BERITA] Error endpoint klasifikasi berita {berita_id}: {exc}")
        return jsonify({"status": "error", "message": "Gagal memperbarui klasifikasi."}), 500
