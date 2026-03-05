"""
Backend Flask untuk Dashboard Berita RadarTegal.
Serve frontend + API scraping + koneksi Supabase.

Jalankan:
    python app.py
    Buka http://localhost:5000
"""

import asyncio
import os
import threading

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from supabase import create_client

from scrape_radartegal import scrape_new_articles

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__, static_folder=".", static_url_path="")

# Flag untuk mencegah scraping paralel
_scraping_lock = threading.Lock()
_scraping_active = False


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
    """Ambil semua berita dari Supabase, urutkan dari terbaru."""
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


# ── API: jalankan scraping ─────────────────────────────────────────────────────

@app.route("/api/scrape", methods=["POST"])
def start_scrape():
    """
    Jalankan scraping berita baru. Berhenti saat menemukan berita lama.
    Hasilnya langsung disimpan ke Supabase.
    """
    global _scraping_active

    if not _scraping_lock.acquire(blocking=False):
        return jsonify({
            "status": "error",
            "message": "Scraping sedang berjalan, tunggu hingga selesai."
        }), 409

    try:
        _scraping_active = True

        body = request.get_json(silent=True) or {}
        max_pages = body.get("max_pages")
        if max_pages is not None:
            max_pages = int(max_pages)

        # Ambil semua URL yang sudah ada di database
        existing = supabase.table("berita").select("url").execute()
        existing_urls = {row["url"] for row in existing.data}
        print(f"[SCRAPE] {len(existing_urls)} berita sudah ada di database.")
        print(f"[SCRAPE] Batas halaman: {max_pages or 'semua'}")

        # Jalankan scraper async di event loop baru
        loop = asyncio.new_event_loop()
        new_articles = loop.run_until_complete(
            scrape_new_articles(existing_urls, headless=True, delay=1.5, max_pages=max_pages)
        )
        loop.close()

        # Simpan ke Supabase
        inserted = 0
        for article in new_articles:
            try:
                supabase.table("berita").insert({
                    "title":   article["title"],
                    "date":    article["date"],
                    "url":     article["url"],
                    "content": article["content"],
                    "tags":    article["tags"],
                }).execute()
                inserted += 1
            except Exception as exc:
                print(f"[DB ERROR] Gagal insert: {article['url']} — {exc}")

        print(f"[SCRAPE] Selesai. {inserted} berita baru disimpan.")
        return jsonify({
            "status": "ok",
            "message": f"{inserted} berita baru berhasil disimpan.",
            "count": inserted,
        })

    except Exception as exc:
        print(f"[SCRAPE ERROR] {exc}")
        return jsonify({"status": "error", "message": str(exc)}), 500

    finally:
        _scraping_active = False
        _scraping_lock.release()


# ── API: status scraping ──────────────────────────────────────────────────────

@app.route("/api/scrape/status", methods=["GET"])
def scrape_status():
    return jsonify({"active": _scraping_active})


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("Dashboard Berita RadarTegal — Flask Server")
    print("=" * 50)
    print(f"Supabase: {SUPABASE_URL}")
    print("Buka http://localhost:5000")
    print()
    app.run(debug=True, port=5000)
