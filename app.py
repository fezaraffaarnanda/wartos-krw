"""
Backend Flask untuk Dashboard Berita.
Serve frontend + API scraping 4 sumber + Supabase + Auth.

Jalankan:
    python app.py
    Buka http://localhost:5000
"""

import os
import threading
from datetime import timedelta

from dotenv import load_dotenv
from flask import (
    Flask, jsonify, redirect, request,
    send_from_directory, url_for,
)
from flask_bcrypt import Bcrypt
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import (
    LoginManager, UserMixin,
    current_user, login_required, login_user, logout_user,
)
from supabase import create_client

from scrapers.scrape_radartegal_bs4 import scrape_new_articles as scrape_radartegal
from scrapers.scraping_panturapost import scrape_new_articles as scrape_panturapost
from scrapers.scrape_tribunjateng_v2 import scrape_new_articles as scrape_tribunjateng
from scrapers.scrape_kompas import scrape_new_articles as scrape_kompas
from utils import normalize_date

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Flask app ──────────────────────────────────────────────────────────────────

app = Flask(__name__, static_folder="static", static_url_path="/static", template_folder="templates")

SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
if not SECRET_KEY:
    import secrets
    SECRET_KEY = secrets.token_hex(32)
    print("[PERINGATAN] FLASK_SECRET_KEY tidak ditemukan di .env — menggunakan kunci acak sementara.")

app.secret_key = SECRET_KEY

# Secure session config
app.config["SESSION_COOKIE_HTTPONLY"]    = True
app.config["SESSION_COOKIE_SAMESITE"]   = "Lax"
app.config["SESSION_COOKIE_SECURE"]     = False   # ubah True jika pakai HTTPS
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=1)

# ── Extensions ─────────────────────────────────────────────────────────────────

bcrypt       = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = "serve_login"

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["300 per hour"],
    storage_uri="memory://",
)


# ── User model ─────────────────────────────────────────────────────────────────

class User(UserMixin):
    def __init__(self, user_id: str, username: str, role: str):
        self.id       = user_id
        self.username = username
        self.role     = role


@login_manager.user_loader
def load_user(user_id: str):
    try:
        result = (
            supabase.table("users")
            .select("id, username, role")
            .eq("id", user_id)
            .single()
            .execute()
        )
        if result.data:
            d = result.data
            return User(str(d["id"]), d["username"], d["role"])
    except Exception:
        pass
    return None


# ── Serve static pages ─────────────────────────────────────────────────────────

@app.route("/login")
def serve_login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    return send_from_directory("templates", "login.html")


@app.route("/")
@login_required
def index():
    return send_from_directory("templates", "index.html")


@app.route("/berita/<int:berita_id>")
@login_required
def berita_detail(berita_id):
    return send_from_directory("templates", "berita.html")


@app.route("/static/css/<path:filename>")
def serve_styles(filename):
    return send_from_directory("static/css", filename)


@app.route("/static/js/<path:filename>")
def serve_scripts(filename):
    return send_from_directory("static/js", filename)


@app.route("/static/bps.svg")
def serve_logo():
    return send_from_directory("static", "bps.svg")


# ── Auth API ───────────────────────────────────────────────────────────────────

@app.route("/api/login", methods=["POST"])
@limiter.limit("5 per 15 minutes")
def api_login():
    data = request.get_json(silent=True) or {}

    username = str(data.get("username", "")).strip()[:100]
    password = str(data.get("password", "")).strip()[:200]

    if not username or not password:
        return jsonify({"status": "error", "message": "Username dan password wajib diisi."}), 400

    try:
        result = (
            supabase.table("users")
            .select("id, username, password_hash, role")
            .eq("username", username)
            .single()
            .execute()
        )
        user_data = result.data
    except Exception:
        user_data = None

    # Pesan generik — tidak membedakan "user tidak ada" vs "password salah"
    if not user_data or not bcrypt.check_password_hash(user_data["password_hash"], password):
        return jsonify({"status": "error", "message": "Username atau password salah."}), 401

    user = User(str(user_data["id"]), user_data["username"], user_data["role"])
    login_user(user, remember=False)

    return jsonify({
        "status": "ok",
        "username": user.username,
        "role":     user.role,
    })


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("serve_login"))


@app.route("/api/me", methods=["GET"])
@login_required
def api_me():
    return jsonify({
        "status":   "ok",
        "username": current_user.username,
        "role":     current_user.role,
    })


# ── API: ambil semua berita ────────────────────────────────────────────────────

@app.route("/api/berita", methods=["GET"])
@login_required
def get_berita():
    try:
        result = (
            supabase.table("berita")
            .select("*")
            .order("id", desc=True)
            .execute()
        )
        return jsonify({"status": "ok", "data": result.data})
    except Exception:
        return jsonify({"status": "error", "message": "Gagal mengambil data."}), 500


@app.route("/api/berita/<int:berita_id>", methods=["GET"])
@login_required
def get_berita_by_id(berita_id):
    if berita_id <= 0:
        return jsonify({"status": "error", "message": "ID tidak valid."}), 400
    try:
        result = (
            supabase.table("berita")
            .select("*")
            .eq("id", berita_id)
            .single()
            .execute()
        )
        if not result.data:
            return jsonify({"status": "error", "message": "Berita tidak ditemukan."}), 404
        return jsonify({"status": "ok", "data": result.data})
    except Exception:
        return jsonify({"status": "error", "message": "Berita tidak ditemukan."}), 404


# ── API: last scrape time ──────────────────────────────────────────────────────

@app.route("/api/last-scrape", methods=["GET"])
@login_required
def get_last_scrape():
    """Kembalikan timestamp artikel terakhir yang diinsert ke database."""
    try:
        result = (
            supabase.table("berita")
            .select("created_at")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            return jsonify({"status": "ok", "last_scrape": result.data[0]["created_at"]})
        return jsonify({"status": "ok", "last_scrape": None})
    except Exception:
        return jsonify({"status": "error", "message": "Gagal mengambil data."}), 500



# ── API: progress scraping ─────────────────────────────────────────────────────

@app.route("/api/scrape/progress", methods=["GET"])
@login_required
def get_progress():
    return jsonify({
        "progress": _scrape_progress,
        "overall":  _scrape_overall,
    })


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
    _scrape_overall["active"]         = True
    _scrape_overall["done"]           = False
    _scrape_overall["total_inserted"] = 0
    _scrape_overall["error"]          = ""


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
        if not article or not article.get("title") or not article.get("url"):
            print(f"[SKIP] {source_key}: artikel null/judul kosong dilewati")
            continue

        # ── Validasi tambahan khusus tribunjateng: tidak ada kolom wajib yang NA/kosong
        if source_key == "tribunjateng":
            for field in ("title", "date", "content"):
                val = article.get(field, "")
                if not val or str(val).strip().upper() == "NA":
                    print(f"[SKIP] {source_key}: field '{field}' kosong/NA — {article.get('url', '')}")
                    article = None
                    break
            if article is None:
                continue

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

        # ── 1. Radar Tegal ────────────────────────────────────────────────────
        _scrape_progress["radartegal"]["status"]  = "running"
        _scrape_progress["radartegal"]["message"] = "Memulai scraping..."

        def rt_progress(count, msg):
            _scrape_progress["radartegal"]["scraped"] = count
            _scrape_progress["radartegal"]["message"] = msg

        max_pages = max(1, max_articles // 30)
        print(f"[SCRAPE] RadarTegal: maks {max_pages} halaman (~{max_articles} artikel)")
        rt_articles = scrape_radartegal(existing_urls, max_pages=max_pages, on_progress=rt_progress)
        n = _insert_articles(rt_articles, "radartegal")
        total_inserted += n
        _scrape_progress["radartegal"]["status"]  = "done"
        _scrape_progress["radartegal"]["message"] = f"Selesai — {n} berita disimpan"
        print(f"[SCRAPE] RadarTegal selesai: {n} disimpan")

        # ── 2. Pantura Post ───────────────────────────────────────────────────
        _scrape_progress["panturapost"]["status"]  = "running"
        _scrape_progress["panturapost"]["message"] = "Memulai scraping..."

        def pp_progress(count, _src):
            _scrape_progress["panturapost"]["scraped"]  = count
            _scrape_progress["panturapost"]["message"] = f"{count} berita ditemukan"

        print(f"[SCRAPE] PanturaPost: maks {max_articles} artikel")
        pp_articles = scrape_panturapost(existing_urls, max_articles=max_articles, on_progress=pp_progress)
        n = _insert_articles(pp_articles, "panturapost")
        total_inserted += n
        _scrape_progress["panturapost"]["status"]  = "done"
        _scrape_progress["panturapost"]["message"] = f"Selesai — {n} berita disimpan"
        print(f"[SCRAPE] PanturaPost selesai: {n} disimpan")

        # ── 3. Tribun Jateng ──────────────────────────────────────────────────
        _scrape_progress["tribunjateng"]["status"]  = "running"
        _scrape_progress["tribunjateng"]["message"] = "Memulai scraping..."

        def tj_progress(count, _src):
            _scrape_progress["tribunjateng"]["scraped"]  = count
            _scrape_progress["tribunjateng"]["message"] = f"{count} berita ditemukan"

        print(f"[SCRAPE] TribunJateng: maks {max_articles} artikel")
        tj_articles = scrape_tribunjateng(existing_urls, max_articles=max_articles, on_progress=tj_progress)
        n = _insert_articles(tj_articles, "tribunjateng")
        total_inserted += n
        _scrape_progress["tribunjateng"]["status"]  = "done"
        _scrape_progress["tribunjateng"]["message"] = f"Selesai — {n} berita disimpan"
        print(f"[SCRAPE] TribunJateng selesai: {n} disimpan")

        # ── 4. Kompas ─────────────────────────────────────────────────────────
        _scrape_progress["kompas"]["status"]  = "running"
        _scrape_progress["kompas"]["message"] = "Memulai scraping..."

        def kp_progress(count, _src):
            _scrape_progress["kompas"]["scraped"]  = count
            _scrape_progress["kompas"]["message"] = f"{count} berita ditemukan"

        print(f"[SCRAPE] Kompas: maks {max_articles} artikel")
        kp_articles = scrape_kompas(existing_urls, max_articles=max_articles, on_progress=kp_progress)
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
@login_required
def start_scrape():
    if current_user.role != "admin":
        return jsonify({"status": "error", "message": "Akses ditolak. Hanya admin yang dapat menjalankan scraping."}), 403

    if not _scraping_lock.acquire(blocking=False):
        return jsonify({
            "status":  "error",
            "message": "Scraping sedang berjalan, tunggu hingga selesai.",
        }), 409

    body         = request.get_json(silent=True) or {}
    max_articles = int(body.get("max_articles", 150))
    max_articles = max(1, min(max_articles, 999))

    _reset_progress()
    t = threading.Thread(target=_scrape_worker, args=(max_articles,), daemon=True)
    t.start()

    return jsonify({"status": "started", "max_articles": max_articles})


# ── API: Vercel Cron ───────────────────────────────────────────────────

@app.route("/api/cron", methods=["GET"])
def cron_scrape():
    """
    Endpoint dipanggil oleh Vercel Cron setiap jam sekali.
    Vercel secara otomatis mengirim header:
        Authorization: Bearer <CRON_SECRET>
    Set CRON_SECRET di Vercel environment variables.
    """
    cron_secret = os.getenv("CRON_SECRET", "")
    auth_header = request.headers.get("Authorization", "")
    expected    = f"Bearer {cron_secret}"

    if not cron_secret or auth_header != expected:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    print("[CRON] Mulai scraping otomatis (Vercel Cron)")
    results = {}
    total_inserted = 0
    errors = []

    try:
        existing = supabase.table("berita").select("url").execute()
        existing_urls = {row["url"] for row in existing.data}
        print(f"[CRON] {len(existing_urls)} URL sudah ada.")
    except Exception as exc:
        return jsonify({"status": "error", "message": f"Gagal fetch existing URLs: {exc}"}), 500

    MAX_PER_SOURCE = 50  # batas per sumber agar tidak timeout di Vercel

    scrapers = [
        ("radartegal",   scrape_radartegal,   {"max_pages": 2}),
        ("panturapost",  scrape_panturapost,  {"max_articles": MAX_PER_SOURCE}),
        ("tribunjateng", scrape_tribunjateng, {"max_articles": MAX_PER_SOURCE}),
        ("kompas",       scrape_kompas,       {"max_articles": MAX_PER_SOURCE}),
    ]

    for key, scraper_fn, kwargs in scrapers:
        try:
            articles = scraper_fn(existing_urls, **kwargs)
            n = _insert_articles(articles, key)
            results[key] = n
            total_inserted += n
            print(f"[CRON] {key}: {n} disimpan")
        except Exception as exc:
            errors.append(f"{key}: {exc}")
            print(f"[CRON ERROR] {key}: {exc}")

    print(f"[CRON] Selesai. Total {total_inserted} berita baru disimpan.")
    return jsonify({
        "status":         "ok",
        "total_inserted": total_inserted,
        "results":        results,
        "errors":         errors,
    })


# ── Error handlers ─────────────────────────────────────────────────────────────

@app.errorhandler(401)
def unauthorized(e):
    if request.path.startswith("/api/"):
        return jsonify({"status": "error", "message": "Sesi habis. Silakan login kembali."}), 401
    return redirect(url_for("serve_login"))


@app.errorhandler(403)
def forbidden(e):
    return jsonify({"status": "error", "message": "Akses ditolak."}), 403


@app.errorhandler(429)
def rate_limit_exceeded(e):
    return jsonify({"status": "error", "message": "Terlalu banyak percobaan. Coba lagi dalam beberapa menit."}), 429


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("Dashboard Berita — Flask Server (4 Sumber)")
    print("=" * 50)
    print(f"Supabase: {SUPABASE_URL}")
    print("Buka http://localhost:5000")
    print()
    app.run(debug=True, port=5000, use_reloader=False)
