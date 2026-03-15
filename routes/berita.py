"""
Blueprint: API data berita.
"""

from flask import Blueprint, jsonify
from flask_login import login_required

from core.db_helpers import (
    BERITA_LIST_COLUMNS,
    BERITA_EXPORT_COLUMNS,
    _build_berita_query,
    _parse_filter_params,
)
from core.db import supabase

berita_bp = Blueprint("berita", __name__)


@berita_bp.route("/api/berita", methods=["GET"])
@login_required
def get_berita():
    """
    Kembalikan daftar berita TANPA kolom content (berat).
    Query params opsional: search, date_from, date_to (format YYYY-MM-DD)
    """
    search, date_from, date_to = _parse_filter_params()
    try:
        result = _build_berita_query(BERITA_LIST_COLUMNS, search, date_from, date_to).execute()
        return jsonify({"status": "ok", "data": result.data})
    except Exception:
        return jsonify({"status": "error", "message": "Gagal mengambil data."}), 500


@berita_bp.route("/api/berita/export", methods=["GET"])
@login_required
def export_berita():
    """
    Endpoint khusus untuk download Excel — termasuk kolom content.
    Dipanggil hanya saat user klik Download Excel.
    """
    search, date_from, date_to = _parse_filter_params()
    try:
        result = _build_berita_query(BERITA_EXPORT_COLUMNS, search, date_from, date_to).execute()
        return jsonify({"status": "ok", "data": result.data})
    except Exception:
        return jsonify({"status": "error", "message": "Gagal mengekspor data."}), 500


@berita_bp.route("/api/berita/years", methods=["GET"])
@login_required
def get_berita_years():
    """Kembalikan list tahun unik yang ada di kolom date_parsed, diurutkan descending."""
    try:
        result = (
            supabase.table("berita")
            .select("date_parsed")
            .not_.is_("date_parsed", "null")
            .execute()
        )
        years = sorted(
            {str(row["date_parsed"])[:4] for row in result.data if row.get("date_parsed")},
            reverse=True,
        )
        return jsonify({"status": "ok", "years": years})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@berita_bp.route("/api/berita/<int:berita_id>", methods=["GET"])
@login_required
def get_berita_by_id(berita_id):
    if berita_id <= 0:
        return jsonify({"status": "error", "message": "ID tidak valid."}), 400
    try:
        result = (
            supabase.table("berita")
            .select("*")
            .eq("id", berita_id)
            .single()
            .execute()
        )
        if not result.data:
            return jsonify({"status": "error", "message": "Berita tidak ditemukan."}), 404
        return jsonify({"status": "ok", "data": result.data})
    except Exception:
        return jsonify({"status": "error", "message": "Berita tidak ditemukan."}), 404
