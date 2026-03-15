"""
Helper fungsi query Supabase yang dipakai oleh lebih dari satu modul.

Semua fungsi menggunakan `supabase` dari core.db agar tidak perlu
menerima client sebagai parameter di setiap pemanggilan.
"""

import time
from datetime import datetime, timezone, timedelta

from flask import request

from core.db import supabase

# ── Konstanta ───────────────────────────────────────────────────────────────

BERITA_LIST_COLUMNS   = "id, title, date, date_parsed, url, tags, kbli, aktivitas_ekonomi, source, created_at"
BERITA_EXPORT_COLUMNS = "id, title, date, date_parsed, url, tags, kbli, aktivitas_ekonomi, source, content"

WIB = timezone(timedelta(hours=7))


# ── Berita ──────────────────────────────────────────────────────────────────

def _build_berita_query(columns: str, search: str, date_from: str, date_to: str):
    """Buat Supabase query dengan filter opsional."""
    query = (
        supabase.table("berita")
        .select(columns)
        .order("date_parsed", desc=True, nullsfirst=False)
    )
    if search:
        query = query.or_(f"title.ilike.%{search}%,tags.ilike.%{search}%,kbli.ilike.%{search}%")
    if date_from:
        query = query.gte("date_parsed", date_from)
    if date_to:
        query = query.lte("date_parsed", date_to)
    return query


def _parse_filter_params() -> tuple[str, str, str]:
    """Ekstrak dan sanitasi filter params dari request."""
    return (
        request.args.get("search",    "").strip(),
        request.args.get("date_from", "").strip(),
        request.args.get("date_to",   "").strip(),
    )


def _fetch_existing_urls() -> set:
    """Ambil semua URL berita dari DB untuk deduplikasi scraping."""
    result = supabase.table("berita").select("url").execute()
    return {row["url"] for row in result.data}


# ── Scrape log ──────────────────────────────────────────────────────────────

def _log_scrape_run(total_inserted: int) -> None:
    """Insert satu baris ke scrape_log. Gagal diam-diam agar tidak mengganggu flow."""
    try:
        supabase.table("scrape_log").insert({"total_inserted": total_inserted}).execute()
    except Exception as exc:
        print(f"[LOG] Gagal catat scrape_log: {exc}")


def _fetch_last_scrape_timestamp() -> str | None:
    result = (
        supabase.table("scrape_log")
        .select("scraped_at")
        .order("scraped_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0]["scraped_at"] if result.data else None


def _count_todays_articles() -> int:
    today_str = datetime.now(WIB).strftime("%Y-%m-%d")
    result = (
        supabase.table("berita")
        .select("id", count="exact")
        .eq("date_parsed", today_str)
        .execute()
    )
    return result.count or 0


# ── AI Insights DB ──────────────────────────────────────────────────────────

def _fetch_period_articles(date_from: str, date_to: str) -> list[dict]:
    """Ambil berita pada rentang tanggal tertentu dari Supabase."""
    result = (
        supabase.table("berita")
        .select("title, date, url, content, tags, source")
        .gte("date_parsed", date_from)
        .lte("date_parsed", date_to)
        .order("date_parsed", desc=True)
        .execute()
    )
    return result.data or []


def _load_insight_from_db(period_key: str) -> dict | None:
    """Cek apakah ada insight tersimpan di DB untuk period_key ini."""
    try:
        result = (
            supabase.table("ai_insights")
            .select("pdrb, kemiskinan, pengangguran, sources_json, article_count, period_label, created_at")
            .eq("period_key", period_key)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            row = result.data[0]
            return {
                "pdrb":          row["pdrb"],
                "kemiskinan":    row["kemiskinan"],
                "pengangguran":  row["pengangguran"],
                "sources":       row["sources_json"] or {},
                "article_count": row["article_count"],
                "period_label":  row["period_label"],
                "created_at":    row["created_at"],
            }
    except Exception as exc:
        print(f"[AI Insights] Gagal baca dari DB: {exc}")
    return None


def _save_insight_to_db(period_key: str, period_label: str, insights: dict, article_count: int) -> None:
    """Simpan hasil insight ke tabel ai_insights."""
    try:
        supabase.table("ai_insights").insert({
            "period_key":    period_key,
            "period_label":  period_label,
            "pdrb":          insights.get("pdrb", ""),
            "kemiskinan":    insights.get("kemiskinan", ""),
            "pengangguran":  insights.get("pengangguran", ""),
            "sources_json":  insights.get("sources", {}),
            "article_count": article_count,
        }).execute()
        print(f"[AI Insights] Hasil disimpan ke DB (period_key={period_key}).")
    except Exception as exc:
        print(f"[AI Insights] Gagal simpan ke DB: {exc}")


# ── AI Chat DB ──────────────────────────────────────────────────────────────

def _get_or_create_chat_session(user_id: int) -> dict:
    """Ambil session terbaru milik user, atau buat baru jika belum ada."""
    result = (
        supabase.table("ai_chat_sessions")
        .select("id, user_id, title, created_at, updated_at")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]

    created = (
        supabase.table("ai_chat_sessions")
        .insert({"user_id": user_id, "title": "Percakapan AI"})
        .execute()
    )
    return created.data[0]


def _create_chat_session(user_id: int) -> dict:
    created = (
        supabase.table("ai_chat_sessions")
        .insert({"user_id": user_id, "title": "Percakapan AI"})
        .execute()
    )
    return created.data[0]


def _get_chat_session_owned(user_id: int, session_id: int) -> dict | None:
    try:
        result = (
            supabase.table("ai_chat_sessions")
            .select("id, user_id, title, created_at, updated_at")
            .eq("id", session_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        return result.data
    except Exception:
        return None


def _load_chat_history(session_id: int, limit: int = 30) -> list[dict]:
    result = (
        supabase.table("ai_chat_messages")
        .select("id, role, content, citations_json, created_at")
        .eq("session_id", session_id)
        .order("created_at", desc=False)
        .limit(limit)
        .execute()
    )
    return result.data or []


def _save_chat_message(
    session_id: int,
    role: str,
    content: str,
    citations: list[dict] | None = None,
) -> None:
    supabase.table("ai_chat_messages").insert({
        "session_id":    session_id,
        "role":          role,
        "content":       content,
        "citations_json": citations or [],
    }).execute()

    supabase.table("ai_chat_sessions").update({
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", session_id).execute()
