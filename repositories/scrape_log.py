"""
Repository scrape log.
"""

from datetime import datetime

from clients.supabase import supabase
from utils.date import WIB


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
