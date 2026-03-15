"""
Shared mutable state lintas modul/thread.

Semua dict di-mutate in-place (bukan di-reassign) sehingga aman diimport
sebagai reference dari modul mana pun tanpa khawatir stale reference.
"""

import threading

# ── Scraping state ──────────────────────────────────────────────────────────

_scraping_lock = threading.Lock()

_scrape_progress: dict = {
    "radartegal":   {"status": "idle", "scraped": 0, "inserted": 0, "message": "Menunggu..."},
    "panturapost":  {"status": "idle", "scraped": 0, "inserted": 0, "message": "Menunggu..."},
    "tribunjateng": {"status": "idle", "scraped": 0, "inserted": 0, "message": "Menunggu..."},
    "kompas":       {"status": "idle", "scraped": 0, "inserted": 0, "message": "Menunggu..."},
    "setdategal":   {"status": "idle", "scraped": 0, "inserted": 0, "message": "Menunggu..."},
}

_scrape_overall: dict = {"active": False, "done": False, "total_inserted": 0, "error": ""}


def _reset_progress() -> None:
    for key in _scrape_progress:
        _scrape_progress[key] = {"status": "idle", "scraped": 0, "inserted": 0, "message": "Menunggu..."}
    _scrape_overall.update({"active": True, "done": False, "total_inserted": 0, "error": ""})


# ── AI Insights cache ───────────────────────────────────────────────────────

# Cache in-memory per actor_period_key: { key: {"data": ..., "ts": float} }
_INSIGHTS_CACHE: dict = {}
_INSIGHTS_CACHE_TTL   = 60 * 60  # 1 jam

# Status generasi background per actor_period_key:
#   False / key tidak ada  → belum pernah / siap generate baru
#   True                   → thread sedang berjalan
#   "error: <pesan>"       → thread terakhir gagal
_INSIGHTS_GENERATING: dict[str, bool | str] = {}
