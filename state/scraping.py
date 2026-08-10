"""
Shared mutable state untuk alur scraping.
"""

import threading

from config.region import SOURCE_KEYS

_scraping_lock = threading.Lock()

_IDLE_PROGRESS = {"status": "idle", "scraped": 0, "inserted": 0, "message": "Menunggu..."}

_scrape_progress: dict = {key: dict(_IDLE_PROGRESS) for key in SOURCE_KEYS}

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
