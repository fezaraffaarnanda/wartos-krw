"""
Shared mutable state untuk alur scraping.
"""

import threading

_scraping_lock = threading.Lock()

_scrape_progress: dict = {
    "inews_karawang": {"status": "idle", "scraped": 0, "inserted": 0, "message": "Menunggu..."},
    "karawangnews": {"status": "idle", "scraped": 0, "inserted": 0, "message": "Menunggu..."},
    "pemda_karawang": {"status": "idle", "scraped": 0, "inserted": 0, "message": "Menunggu..."},
    "radar_karawang": {"status": "idle", "scraped": 0, "inserted": 0, "message": "Menunggu..."},
}

_scrape_overall: dict = {"active": False, "done": False, "total_inserted": 0, "error": ""}


def _reset_progress() -> None:
    for key in _scrape_progress:
        _scrape_progress[key] = {
            "status": "idle",
            "scraped": 0,
            "inserted": 0,
            "message": "Menunggu...",
        }
    _scrape_overall.update({"active": True, "done": False, "total_inserted": 0, "error": ""})
