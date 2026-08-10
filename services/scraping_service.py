"""
Service layer untuk kontrol scraping.
"""

import threading
from typing import Any

from config.region import NEWS_SOURCES
from config.settings import get_settings
from repositories.scrape_log import ScrapeLogRepository
from schemas.scraping import NewsSourceOut
from services.article_pipeline import _classifiers, _run_kbli_backfill, _scrape_sync, _scrape_worker
from state.scraping import _reset_progress, _scrape_overall, _scrape_progress, _scraping_lock


class ScrapingService:
    """Use-case scraping untuk endpoint dashboard dan cron."""

    def __init__(self, scrape_log_repository: ScrapeLogRepository | None = None):
        self._scrape_log_repo = scrape_log_repository or ScrapeLogRepository()

    def is_valid_api_key(self, authorization_header: str) -> bool:
        settings = get_settings()
        cron_secret = str(settings.CRON_SECRET or "").strip()
        if not cron_secret:
            return False
        return authorization_header == f"Bearer {cron_secret}"

    def get_progress(self) -> dict[str, Any]:
        return {"progress": _scrape_progress, "overall": _scrape_overall}

    def list_sources(self) -> tuple[dict[str, Any], int]:
        """Daftar sumber berita aktif — dipakai UI untuk merender chip & baris progres."""
        data = [
            NewsSourceOut.model_validate({"key": key, "label": label}).model_dump()
            for key, label in NEWS_SOURCES
        ]
        return {"status": "ok", "data": data}, 200

    def get_last_scrape(self) -> tuple[dict[str, Any], int]:
        try:
            last_scrape = self._scrape_log_repo.fetch_last_scrape_timestamp()
            new_count = self._scrape_log_repo.count_todays_articles()
            return {
                "status": "ok",
                "last_scrape": last_scrape,
                "new_count": new_count,
            }, 200
        except Exception as exc:
            return {"status": "error", "message": str(exc)}, 500

    def start_scrape(self, *, max_articles: int, is_api_key: bool) -> tuple[dict[str, Any], int]:
        if is_api_key:
            print(
                "[SCRAPE] Dipanggil via API key "
                f"- mode synchronous, maks {max_articles} artikel"
            )
            result = _scrape_sync(max_articles)
            status_code = 200 if result.get("status") == "ok" else 500
            return result, status_code

        if not _scraping_lock.acquire(blocking=False):
            return {
                "status": "error",
                "message": "Scraping sedang berjalan, tunggu hingga selesai.",
            }, 409

        _reset_progress()
        threading.Thread(
            target=_scrape_worker,
            args=(max_articles,),
            daemon=True,
            name="scrape-worker-manual",
        ).start()
        return {"status": "started", "max_articles": max_articles}, 200

    def trigger_kbli_backfill(self, *, is_admin: bool) -> tuple[dict[str, Any], int]:
        if not is_admin:
            return {"status": "error", "message": "Akses ditolak. Hanya admin."}, 403

        if _classifiers["kbli_predictor"] is None:
            return {
                "status": "error",
                "message": "KBLI Classifier tidak tersedia. Periksa GEMINI_API_KEY dan koneksi Supabase.",
            }, 503

        threading.Thread(
            target=_run_kbli_backfill,
            daemon=True,
            name="kbli-backfill-manual",
        ).start()
        return {
            "status": "started",
            "message": "Backfill KBLI dimulai di background.",
        }, 200
