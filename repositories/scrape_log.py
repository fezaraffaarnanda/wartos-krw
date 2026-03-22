"""
Repository scrape log.
"""

from datetime import datetime

from repositories.base import BaseRepository
from utils.date import WIB


class ScrapeLogRepository(BaseRepository):
    """Akses data scrape_log dan statistik scraping harian."""

    def log_scrape_run(self, total_inserted: int) -> None:
        try:
            self._supabase.table("scrape_log").insert(
                {"total_inserted": total_inserted}
            ).execute()
        except Exception as exc:
            print(f"[LOG] Gagal catat scrape_log: {exc}")

    def fetch_last_scrape_timestamp(self) -> str | None:
        result = (
            self._supabase.table("scrape_log")
            .select("scraped_at")
            .order("scraped_at", desc=True)
            .limit(1)
            .execute()
        )
        return result.data[0]["scraped_at"] if result.data else None

    def count_todays_articles(self) -> int:
        today_str = datetime.now(WIB).strftime("%Y-%m-%d")
        result = (
            self._supabase.table("berita")
            .select("id", count="exact")
            .eq("date_parsed", today_str)
            .execute()
        )
        return result.count or 0


def _log_scrape_run(total_inserted: int) -> None:
    """Insert satu baris ke scrape_log. Gagal diam-diam agar tidak mengganggu flow."""
    ScrapeLogRepository().log_scrape_run(total_inserted)


def _fetch_last_scrape_timestamp() -> str | None:
    return ScrapeLogRepository().fetch_last_scrape_timestamp()


def _count_todays_articles() -> int:
    return ScrapeLogRepository().count_todays_articles()
