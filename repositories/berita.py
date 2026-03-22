"""
Repository berita.
"""

from clients.supabase import supabase

BERITA_LIST_COLUMNS = "id, title, date, date_parsed, url, tags, kbli, aktivitas_ekonomi, source, created_at"
BERITA_EXPORT_COLUMNS = "id, title, date, date_parsed, url, tags, kbli, aktivitas_ekonomi, source, content"


def _fetch_existing_urls() -> set[str]:
    """Ambil semua URL berita dari DB untuk deduplikasi scraping."""
    result = supabase.table("berita").select("url").execute()
    return {row["url"] for row in (result.data or []) if row.get("url")}
