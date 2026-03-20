"""
Blueprint: API data berita + data dashboard overview.
"""

from datetime import datetime, timedelta
from typing import Any, cast

from flask import Blueprint, jsonify, request
from flask_login import login_required

from core.db import supabase
from core.db_helpers import BERITA_EXPORT_COLUMNS, BERITA_LIST_COLUMNS

berita_bp = Blueprint("berita", __name__)

_SORT_MAP = {
    "date": "date_parsed",
    "date_parsed": "date_parsed",
    "title": "title",
    "source": "source",
    "tags": "tags",
    "created_at": "created_at",
}


def _parse_filter_params() -> tuple[str, str, str, str, str]:
    return (
        request.args.get("search", "").strip(),
        request.args.get("date_from", "").strip(),
        request.args.get("date_to", "").strip(),
        request.args.get("kbli_code", "").strip().upper(),
        request.args.get("aktivitas_code", "").strip(),
    )


def _safe_int_param(name: str, default: int, min_value: int, max_value: int) -> int:
    raw = request.args.get(name, "").strip()
    if not raw:
        return default
    if not raw.isdigit():
        return default
    return max(min_value, min(int(raw), max_value))


def _safe_sort_param() -> tuple[str, bool, str]:
    sort_by_req = request.args.get("sort_by", "date_parsed").strip().lower()
    sort_col = _SORT_MAP.get(sort_by_req, "date_parsed")
    sort_dir = request.args.get("sort_dir", "desc").strip().lower()
    sort_desc = sort_dir != "asc"
    return sort_col, sort_desc, "desc" if sort_desc else "asc"


def _apply_berita_filters(
    query,
    search: str,
    date_from: str,
    date_to: str,
    kbli_code: str,
    aktivitas_code: str,
):
    if search:
        query = query.or_(
            f"title.ilike.%{search}%,tags.ilike.%{search}%,kbli.ilike.%{search}%"
        )
    if date_from:
        query = query.gte("date_parsed", date_from)
    if date_to:
        query = query.lte("date_parsed", date_to)
    if kbli_code:
        query = query.ilike("kbli", f"{kbli_code}/%")
    if aktivitas_code:
        query = query.ilike("aktivitas_ekonomi", f"{aktivitas_code}/%")
    return query


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
    search, date_from, date_to, kbli_code, aktivitas_code = _parse_filter_params()
    page = _safe_int_param("page", default=1, min_value=1, max_value=50000)
    per_page = _safe_int_param("per_page", default=15, min_value=1, max_value=100)
    sort_col, sort_desc, sort_dir = _safe_sort_param()

    start = (page - 1) * per_page
    end = start + per_page - 1

    try:
        berita_table = cast(Any, supabase.table("berita"))
        query = (
            berita_table.select(BERITA_LIST_COLUMNS, count="exact")  # pyright: ignore[reportArgumentType]
            .order(sort_col, desc=sort_desc, nullsfirst=False)
        )
        query = _apply_berita_filters(
            query,
            search,
            date_from,
            date_to,
            kbli_code,
            aktivitas_code,
        )
        result = query.range(start, end).execute()

        total_items = result.count or 0
        total_pages = max(1, (total_items + per_page - 1) // per_page)

        return jsonify(
            {
                "status": "ok",
                "data": result.data or [],
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total_items": total_items,
                    "total_pages": total_pages,
                    "has_prev": page > 1,
                    "has_next": page < total_pages,
                },
                "filters": {
                    "search": search,
                    "date_from": date_from,
                    "date_to": date_to,
                    "sort_by": sort_col,
                    "sort_dir": sort_dir,
                    "kbli_code": kbli_code,
                    "aktivitas_code": aktivitas_code,
                },
            }
        )
    except Exception:
        return jsonify({"status": "error", "message": "Gagal mengambil data."}), 500


@berita_bp.route("/api/dashboard/overview/summary", methods=["GET"])
@login_required
def get_dashboard_overview_summary():
    """Ringkasan statistik dashboard untuk 30 hari terakhir (ringan, tanpa tabel lengkap)."""
    now = datetime.now()
    cutoff = (now - timedelta(days=30)).date().isoformat()
    month_prefix = now.strftime("%Y-%m")

    try:
        result = (
            supabase.table("berita")
            .select("id, date, date_parsed, tags, kbli")
            .gte("date_parsed", cutoff)
            .order("date_parsed", desc=True, nullsfirst=False)
            .execute()
        )
        rows: list[dict[str, Any]] = [
            cast(dict[str, Any], row)
            for row in (result.data or [])
            if isinstance(row, dict)
        ]

        total_30d = len(rows)
        latest_date = rows[0].get("date") if rows else None

        kbli_count: dict[str, int] = {}
        tag_count: dict[str, int] = {}
        month_tag_count: dict[str, int] = {}

        for row in rows:
            raw_kbli = str(row.get("kbli") or "").strip()
            if raw_kbli and raw_kbli.lower() not in {"tidak relevan", "-", "—"}:
                kode = raw_kbli.split("/")[0].strip().upper()
                if kode:
                    kbli_count[kode] = kbli_count.get(kode, 0) + 1

            raw_tags = str(row.get("tags") or "").strip()
            if raw_tags:
                tags = [
                    t.strip().replace("#", "")
                    for t in raw_tags.replace(",", "|").split("|")
                    if t.strip()
                ]
                for tag in tags:
                    key = tag.lower()
                    tag_count[key] = tag_count.get(key, 0) + 1

                    date_parsed = str(row.get("date_parsed") or "")
                    if date_parsed.startswith(month_prefix):
                        month_tag_count[key] = month_tag_count.get(key, 0) + 1

        top_kbli = sorted(kbli_count.items(), key=lambda x: x[1], reverse=True)[:5]
        top_tags_30d = sorted(tag_count.items(), key=lambda x: x[1], reverse=True)[:5]
        top_tags_month = sorted(month_tag_count.items(), key=lambda x: x[1], reverse=True)[:5]

        return jsonify(
            {
                "status": "ok",
                "data": {
                    "total_30d": total_30d,
                    "latest_date": latest_date,
                    "top_kbli": [{"code": k, "count": v} for k, v in top_kbli],
                    "top_tags_30d": [{"tag": k, "count": v} for k, v in top_tags_30d],
                    "top_tags_month": [
                        {"tag": k, "count": v} for k, v in top_tags_month
                    ],
                },
            }
        )
    except Exception:
        return jsonify({"status": "error", "message": "Gagal mengambil ringkasan dashboard."}), 500


@berita_bp.route("/api/berita/export", methods=["GET"])
@login_required
def export_berita():
    """Endpoint khusus download Excel (termasuk kolom content)."""
    search, date_from, date_to, kbli_code, aktivitas_code = _parse_filter_params()
    try:
        query = supabase.table("berita").select(BERITA_EXPORT_COLUMNS).order(
            "date_parsed", desc=True, nullsfirst=False
        )
        query = _apply_berita_filters(
            query,
            search,
            date_from,
            date_to,
            kbli_code,
            aktivitas_code,
        )
        result = query.execute()
        return jsonify({"status": "ok", "data": result.data or []})
    except Exception:
        return jsonify({"status": "error", "message": "Gagal mengekspor data."}), 500


@berita_bp.route("/api/berita/years", methods=["GET"])
@login_required
def get_berita_years():
    """Kembalikan list tahun unik yang ada di kolom date_parsed, urut DESC."""
    try:
        result = (
            supabase.table("berita")
            .select("date_parsed")
            .not_.is_("date_parsed", "null")
            .execute()
        )
        rows: list[dict[str, Any]] = [
            cast(dict[str, Any], row)
            for row in (result.data or [])
            if isinstance(row, dict)
        ]
        years = sorted(
            {str(row.get("date_parsed"))[:4] for row in rows if row.get("date_parsed")},
            reverse=True,
        )
        return jsonify({"status": "ok", "years": years})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@berita_bp.route("/api/dashboard/data/filter-options", methods=["GET"])
@login_required
def get_dashboard_data_filter_options():
    """Ambil opsi filter KBLI dan Aktivitas dari data yang tersedia."""
    try:
        result = supabase.table("berita").select("kbli, aktivitas_ekonomi").execute()
        rows: list[dict[str, Any]] = [
            cast(dict[str, Any], row)
            for row in (result.data or [])
            if isinstance(row, dict)
        ]

        kbli_codes: set[str] = set()
        aktivitas_codes: set[str] = set()

        for row in rows:
            raw_kbli = str(row.get("kbli") or "").strip()
            if raw_kbli and raw_kbli.lower() not in {"tidak relevan", "-", "—"}:
                code = raw_kbli.split("/")[0].strip().upper()
                if code:
                    kbli_codes.add(code)

            raw_aktivitas = str(row.get("aktivitas_ekonomi") or "").strip()
            if raw_aktivitas and raw_aktivitas != "—":
                code = raw_aktivitas.split("/")[0].strip()
                if code.isdigit():
                    aktivitas_codes.add(code)

        return jsonify(
            {
                "status": "ok",
                "data": {
                    "kbli_codes": sorted(kbli_codes),
                    "aktivitas_codes": sorted(aktivitas_codes, key=lambda x: int(x)),
                },
            }
        )
    except Exception:
        return jsonify({"status": "error", "message": "Gagal mengambil opsi filter."}), 500


@berita_bp.route("/api/berita/<int:berita_id>", methods=["GET"])
@login_required
def get_berita_by_id(berita_id: int):
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
