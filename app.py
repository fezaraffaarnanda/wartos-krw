"""
Backend Flask untuk Dashboard Berita RadarTegal.
Serve frontend + API scraping 3 sumber + koneksi Supabase.

Jalankan:
    python app.py
    Buka http://localhost:5000
"""

import os
import threading

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from supabase import create_client

from scrape_radartegal_bs4 import scrape_new_articles as scrape_radartegal
from scraping_panturapost import scrape_new_articles as scrape_panturapost
from scrape_tribunjateng import scrape_new_articles as scrape_tribunjateng
from scrape_kompas import scrape_new_articles as scrape_kompas
from utils import normalize_date

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__, static_folder=".", static_url_path="")

# ── State scraping ─────────────────────────────────────────────────────────────

_scraping_lock = threading.Lock()

_scrape_progress = {
    "radartegal":   {"status": "idle", "scraped": 0, "inserted": 0, "message": "Menunggu..."},
    "panturapost":  {"status": "idle", "scraped": 0, "inserted": 0, "message": "Menunggu..."},
    "tribunjateng": {"status": "idle", "scraped": 0, "inserted": 0, "message": "Menunggu..."},
    "kompas":       {"status": "idle", "scraped": 0, "inserted": 0, "message": "Menunggu..."},
}
_scrape_overall = {"active": False, "done": False, "total_inserted": 0, "error": ""}


def _reset_progress():
    for key in _scrape_progress:
        _scrape_progress[key] = {"status": "idle", "scraped": 0, "inserted": 0, "message": "Menunggu..."}
    _scrape_overall["active"]        = True
    _scrape_overall["done"]          = False
    _scrape_overall["total_inserted"] = 0
    _scrape_overall["error"]         = ""


# ── Serve frontend ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/styles/<path:filename>")
def serve_styles(filename):
    return send_from_directory("styles", filename)


@app.route("/script/<path:filename>")
def serve_scripts(filename):
    return send_from_directory("script", filename)


@app.route("/bps.svg")
def serve_logo():
    return send_from_directory(".", "bps.svg")


# ── API: ambil semua berita ────────────────────────────────────────────────────

@app.route("/api/berita", methods=["GET"])
def get_berita():
    try:
        result = (
            supabase.table("berita")
            .select("*")
            .order("id", desc=True)
            .execute()
        )
        return jsonify({"status": "ok", "data": result.data})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


# ── API: progress scraping ─────────────────────────────────────────────────────

@app.route("/api/scrape/progress", methods=["GET"])
def get_progress():
    return jsonify({
        "progress": _scrape_progress,
        "overall":  _scrape_overall,
    })


# ── Helper: insert batch ke Supabase ──────────────────────────────────────────

SOURCE_LABELS = {
    "radartegal":   "Radar Tegal",
    "panturapost":  "Pantura Post",
    "tribunjateng": "Tribun Jateng",
    "kompas":       "Kompas",
}


def _insert_articles(articles: list, source_key: str) -> int:
    source_label = SOURCE_LABELS.get(source_key, source_key)
    inserted = 0
    for article in articles:
        try:
            supabase.table("berita").insert({
                "title":   article["title"],
                "date":    normalize_date(article["date"]),
                "url":     article["url"],
                "content": article["content"],
                "tags":    article["tags"],
                "source":  article.get("source") or source_label,
            }).execute()
            inserted += 1
        except Exception as exc:
            print(f"[DB ERROR] {source_key}: {article.get('url', '')} — {exc}")
    _scrape_progress[source_key]["inserted"] = inserted
    return inserted


# ── Worker thread ──────────────────────────────────────────────────────────────

def _scrape_worker(max_articles: int):
    global _scrape_overall

    try:
        existing = supabase.table("berita").select("url").execute()
        existing_urls = {row["url"] for row in existing.data}
        print(f"[SCRAPE] {len(existing_urls)} URL sudah ada di database.")

        total_inserted = 0

        # ── 1. Radar Tegal (requests + BS4 / sync) ────────────────────────────
        _scrape_progress["radartegal"]["status"]  = "running"
        _scrape_progress["radartegal"]["message"] = "Memulai scraping..."

        def rt_progress(count, msg):
            _scrape_progress["radartegal"]["scraped"] = count
            _scrape_progress["radartegal"]["message"] = msg

        max_pages = max(1, max_articles // 30)
        print(f"[SCRAPE] RadarTegal: maks {max_pages} halaman (~{max_articles} artikel)")

        rt_articles = scrape_radartegal(
            existing_urls,
            max_pages=max_pages,
            on_progress=rt_progress,
        )

        n = _insert_articles(rt_articles, "radartegal")
        total_inserted += n
        _scrape_progress["radartegal"]["status"]  = "done"
        _scrape_progress["radartegal"]["message"] = f"Selesai — {n} berita disimpan"
        print(f"[SCRAPE] RadarTegal selesai: {n} disimpan")

        # ── 2. Pantura Post (requests / sync) ─────────────────────────────────
        _scrape_progress["panturapost"]["status"]  = "running"
        _scrape_progress["panturapost"]["message"] = "Memulai scraping..."

        def pp_progress(count, _src):
            _scrape_progress["panturapost"]["scraped"]  = count
            _scrape_progress["panturapost"]["message"] = f"{count} berita ditemukan"

        print(f"[SCRAPE] PanturaPost: maks {max_articles} artikel")
        pp_articles = scrape_panturapost(
            existing_urls,
            max_articles=max_articles,
            on_progress=pp_progress,
        )

        n = _insert_articles(pp_articles, "panturapost")
        total_inserted += n
        _scrape_progress["panturapost"]["status"]  = "done"
        _scrape_progress["panturapost"]["message"] = f"Selesai — {n} berita disimpan"
        print(f"[SCRAPE] PanturaPost selesai: {n} disimpan")

        # ── 3. Tribun Jateng (requests / sync) ────────────────────────────────
        _scrape_progress["tribunjateng"]["status"]  = "running"
        _scrape_progress["tribunjateng"]["message"] = "Memulai scraping..."

        def tj_progress(count, _src):
            _scrape_progress["tribunjateng"]["scraped"]  = count
            _scrape_progress["tribunjateng"]["message"] = f"{count} berita ditemukan"

        print(f"[SCRAPE] TribunJateng: maks {max_articles} artikel")
        tj_articles = scrape_tribunjateng(
            existing_urls,
            max_articles=max_articles,
            on_progress=tj_progress,
        )

        n = _insert_articles(tj_articles, "tribunjateng")
        total_inserted += n
        _scrape_progress["tribunjateng"]["status"]  = "done"
        _scrape_progress["tribunjateng"]["message"] = f"Selesai — {n} berita disimpan"
        print(f"[SCRAPE] TribunJateng selesai: {n} disimpan")

        # ── 4. Kompas (requests / sync) ───────────────────────────────────────
        _scrape_progress["kompas"]["status"]  = "running"
        _scrape_progress["kompas"]["message"] = "Memulai scraping..."

        def kp_progress(count, _src):
            _scrape_progress["kompas"]["scraped"]  = count
            _scrape_progress["kompas"]["message"] = f"{count} berita ditemukan"

        print(f"[SCRAPE] Kompas: maks {max_articles} artikel")
        kp_articles = scrape_kompas(
            existing_urls,
            max_articles=max_articles,
            on_progress=kp_progress,
        )

        n = _insert_articles(kp_articles, "kompas")
        total_inserted += n
        _scrape_progress["kompas"]["status"]  = "done"
        _scrape_progress["kompas"]["message"] = f"Selesai — {n} berita disimpan"
        print(f"[SCRAPE] Kompas selesai: {n} disimpan")

        _scrape_overall["total_inserted"] = total_inserted
        print(f"[SCRAPE] Semua selesai. Total {total_inserted} berita baru disimpan.")

    except Exception as exc:
        _scrape_overall["error"] = str(exc)
        print(f"[SCRAPE ERROR] {exc}")
        for key in _scrape_progress:
            if _scrape_progress[key]["status"] == "running":
                _scrape_progress[key]["status"]  = "error"
                _scrape_progress[key]["message"] = f"Error: {exc}"

    finally:
        _scrape_overall["active"] = False
        _scrape_overall["done"]   = True
        _scraping_lock.release()


# ── API: jalankan scraping ─────────────────────────────────────────────────────

@app.route("/api/scrape", methods=["POST"])
def start_scrape():
    """
    Jalankan scraping 3 sumber secara berurutan di background thread.
    Langsung return {"status": "started"} agar frontend bisa polling progress.
    """
    if not _scraping_lock.acquire(blocking=False):
        return jsonify({
            "status":  "error",
            "message": "Scraping sedang berjalan, tunggu hingga selesai.",
        }), 409

    body        = request.get_json(silent=True) or {}
    max_articles = int(body.get("max_articles", 150))

    _reset_progress()

    t = threading.Thread(target=_scrape_worker, args=(max_articles,), daemon=True)
    t.start()

    return jsonify({"status": "started", "max_articles": max_articles})


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("Dashboard Berita — Flask Server (4 Sumber)")
    print("=" * 50)
    print(f"Supabase: {SUPABASE_URL}")
    print("Buka http://localhost:5000")
    print()
    app.run(debug=True, port=5000, use_reloader=False)
