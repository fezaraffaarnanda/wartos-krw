"""
Repository AI insights.
"""

from clients.supabase import supabase


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
                "pdrb": row["pdrb"],
                "kemiskinan": row["kemiskinan"],
                "pengangguran": row["pengangguran"],
                "sources": row["sources_json"] or {},
                "article_count": row["article_count"],
                "period_label": row["period_label"],
                "created_at": row["created_at"],
            }
    except Exception as exc:
        print(f"[AI Insights] Gagal baca dari DB: {exc}")
    return None


def _save_insight_to_db(period_key: str, period_label: str, insights: dict, article_count: int) -> None:
    """Simpan hasil insight ke tabel ai_insights."""
    try:
        supabase.table("ai_insights").insert({
            "period_key": period_key,
            "period_label": period_label,
            "pdrb": insights.get("pdrb", ""),
            "kemiskinan": insights.get("kemiskinan", ""),
            "pengangguran": insights.get("pengangguran", ""),
            "sources_json": insights.get("sources", {}),
            "article_count": article_count,
        }).execute()
        print(f"[AI Insights] Hasil disimpan ke DB (period_key={period_key}).")
    except Exception as exc:
        print(f"[AI Insights] Gagal simpan ke DB: {exc}")
