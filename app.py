import os
import secrets
import threading
from datetime import datetime, timedelta, timezone

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
from scrapers.scraping_panturapost  import scrape_new_articles as scrape_panturapost
from scrapers.scrape_tribunjateng_v2 import scrape_new_articles as scrape_tribunjateng
from scrapers.scrape_kompas         import scrape_new_articles as scrape_kompas
from scrapers.scraping_tegal        import scrape_new_articles as scrape_tegal
from utils import normalize_date, parse_date_to_iso
from ai_insights import generate_insights
from embeddings import embed_article
from kbli_utils import load_kbli_predictor, predict_kbli_label

load_dotenv()

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))


# ── Flask app ──────────────────────────────────────────────────────────────────

app = Flask(__name__, static_folder="static", static_url_path="/static", template_folder="templates")

_secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
if not os.getenv("FLASK_SECRET_KEY"):
    print("[PERINGATAN] FLASK_SECRET_KEY tidak ditemukan di .env — menggunakan kunci acak sementara.")

app.secret_key = _secret_key
app.config["SESSION_COOKIE_HTTPONLY"]    = True
app.config["SESSION_COOKIE_SAMESITE"]   = "Lax"
app.config["SESSION_COOKIE_SECURE"]     = False   # ubah True jika pakai HTTPS
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=1)


# ── Extensions ─────────────────────────────────────────────────────────────────

bcrypt        = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = "serve_login"

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["300 per hour"],
    storage_uri="memory://",
)


# ── Constants ──────────────────────────────────────────────────────────────────

SOURCE_LABELS = {
    "radartegal":   "Radar Tegal",
    "panturapost":  "Pantura Post",
    "tribunjateng": "Tribun Jateng",
    "kompas":       "Kompas",
    "setdategal":   "Setda Tegal",
}

BERITA_LIST_COLUMNS  = "id, title, date, date_parsed, url, tags, kbli, source, created_at"
BERITA_EXPORT_COLUMNS = "id, title, date, date_parsed, url, tags, kbli, source, content"

WIB = timezone(timedelta(hours=7))


# ── KBLI predictor ──────────────────────────────────────────────────────────────

_kbli_predictor = load_kbli_predictor(os.getenv("KBLI_MODEL_DIR", "model_kbli"))


# ── User model ─────────────────────────────────────────────────────────────────

class User(UserMixin):
    def __init__(self, user_id: str, username: str, role: str):
        self.id       = user_id
        self.username = username
        self.role     = role


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
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

    return jsonify({"status": "ok", "username": user.username, "role": user.role})


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


# ── Helpers: query builder ─────────────────────────────────────────────────────

def _build_berita_query(columns: str, search: str, date_from: str, date_to: str):
    """Buat Supabase query dengan filter opsional."""
    query = (
        supabase.table("berita")
        .select(columns)
        .order("date_parsed", desc=True, nullsfirst=False)
    )
    if search:
        query = query.or_(f"title.ilike.%{search}%,tags.ilike.%{search}%,kbli.ilike.%{search}%")
    if date_from:
        query = query.gte("date_parsed", date_from)
    if date_to:
        query = query.lte("date_parsed", date_to)
    return query


def _parse_filter_params() -> tuple[str, str, str]:
    """Ekstrak dan sanitasi filter params dari request."""
    return (
        request.args.get("search",    "").strip(),
        request.args.get("date_from", "").strip(),
        request.args.get("date_to",   "").strip(),
    )


# ── API: berita ────────────────────────────────────────────────────────────────

@app.route("/api/berita", methods=["GET"])
@login_required
def get_berita():
    """
    Kembalikan daftar berita TANPA kolom content (berat).
    Kolom content hanya dimuat di /api/berita/<id> atau /api/berita/export.

    Query params opsional: search, date_from, date_to (format YYYY-MM-DD)
    """
    search, date_from, date_to = _parse_filter_params()
    try:
        result = _build_berita_query(BERITA_LIST_COLUMNS, search, date_from, date_to).execute()
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


@app.route("/api/berita/export", methods=["GET"])
@login_required
def export_berita():
    """
    Endpoint khusus untuk download Excel — termasuk kolom content.
    Dipanggil hanya saat user klik Download Excel.
    """
    search, date_from, date_to = _parse_filter_params()
    try:
        result = _build_berita_query(BERITA_EXPORT_COLUMNS, search, date_from, date_to).execute()
        return jsonify({"status": "ok", "data": result.data})
    except Exception:
        return jsonify({"status": "error", "message": "Gagal mengekspor data."}), 500


# ── API: distinct years ───────────────────────────────────────────────────────

@app.route("/api/berita/years", methods=["GET"])
@login_required
def get_berita_years():
    """
    Kembalikan list tahun unik yang ada di kolom date_parsed.
    Diurutkan descending (terbaru dulu).
    """
    try:
        result = (
            supabase.table("berita")
            .select("date_parsed")
            .not_.is_("date_parsed", "null")
            .execute()
        )
        years = sorted(
            {str(row["date_parsed"])[:4] for row in result.data if row.get("date_parsed")},
            reverse=True,
        )
        return jsonify({"status": "ok", "years": years})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


# ── Helpers: AI Insights ──────────────────────────────────────────────────────

# Cache in-memory per period_key: { period_key: {"data": ..., "ts": float} }
_INSIGHTS_CACHE: dict     = {}
_INSIGHTS_CACHE_TTL       = 60 * 60  # 1 jam (setelah itu re-check DB)

# Tracking generasi background per period_key:
#   False / key tidak ada → belum pernah / siap generate baru
#   True                  → thread sedang berjalan
#   "error: <pesan>"      → thread terakhir gagal
_INSIGHTS_GENERATING: dict[str, bool | str] = {}


def _get_period_range(period: str, year: int | None = None) -> tuple[str, str, str]:
    """
    Kembalikan (period_key, period_label, date_from, date_to).

    Opsi period: q1/q2/q3/q4, s1/s2, yearly.
    year: tahun yang dipilih user; default = tahun berjalan.
    """
    now          = datetime.now(WIB)
    current_year = now.year
    y            = year if year else current_year
    month        = now.month

    _PERIODS = {
        "q1":     (f"q1_{y}",     f"Triwulan I {y} (Jan–Mar)",      f"{y}-01-01", f"{y}-03-31"),
        "q2":     (f"q2_{y}",     f"Triwulan II {y} (Apr–Jun)",      f"{y}-04-01", f"{y}-06-30"),
        "q3":     (f"q3_{y}",     f"Triwulan III {y} (Jul–Sep)",     f"{y}-07-01", f"{y}-09-30"),
        "q4":     (f"q4_{y}",     f"Triwulan IV {y} (Okt–Des)",      f"{y}-10-01", f"{y}-12-31"),
        "s1":     (f"s1_{y}",     f"Semester I {y} (Jan–Jun)",       f"{y}-01-01", f"{y}-06-30"),
        "s2":     (f"s2_{y}",     f"Semester II {y} (Jul–Des)",      f"{y}-07-01", f"{y}-12-31"),
        "yearly": (f"yearly_{y}", f"Tahunan {y} (Jan–Des)",          f"{y}-01-01", f"{y}-12-31"),
    }

    if period in _PERIODS:
        return _PERIODS[period]

    # Default: triwulan berjalan (hanya berlaku kalau year == current year)
    if y == current_year:
        if month <= 3:  return _PERIODS["q1"]
        elif month <= 6: return _PERIODS["q2"]
        elif month <= 9: return _PERIODS["q3"]
        else:            return _PERIODS["q4"]

    return _PERIODS["yearly"]


def _fetch_period_articles(date_from: str, date_to: str) -> list[dict]:
    """Ambil berita pada rentang tanggal tertentu dari Supabase."""
    result = (
        supabase.table("berita")
        .select("title, date, url, content, tags, source")
        .gte("date_parsed", date_from)
        .lte("date_parsed", date_to)
        .order("date_parsed", desc=True)
        .execute()
    )
    return result.data or []


def _load_insight_from_db(period_key: str) -> dict | None:
    """Cek apakah ada insight tersimpan di DB untuk period_key ini."""
    try:
        result = (
            supabase.table("ai_insights")
            .select("pdrb, kemiskinan, pengangguran, sources_json, article_count, period_label, created_at")
            .eq("period_key", period_key)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            row = result.data[0]
            return {
                "pdrb":          row["pdrb"],
                "kemiskinan":    row["kemiskinan"],
                "pengangguran":  row["pengangguran"],
                "sources":       row["sources_json"] or {},
                "article_count": row["article_count"],
                "period_label":  row["period_label"],
                "created_at":    row["created_at"],
            }
    except Exception as exc:
        print(f"[AI Insights] Gagal baca dari DB: {exc}")
    return None


def _save_insight_to_db(period_key: str, period_label: str, insights: dict, article_count: int):
    """Simpan hasil insight ke tabel ai_insights."""
    try:
        supabase.table("ai_insights").insert({
            "period_key":    period_key,
            "period_label":  period_label,
            "pdrb":          insights.get("pdrb", ""),
            "kemiskinan":    insights.get("kemiskinan", ""),
            "pengangguran":  insights.get("pengangguran", ""),
            "sources_json":  insights.get("sources", {}),
            "article_count": article_count,
        }).execute()
        print(f"[AI Insights] Hasil disimpan ke DB (period_key={period_key}).")
    except Exception as exc:
        print(f"[AI Insights] Gagal simpan ke DB: {exc}")


def _generate_insights_worker(
    period_key:   str,
    period_label: str,
    date_from:    str,
    date_to:      str,
    articles:     list,
):
    """
    Worker thread: jalankan generate_insights() di background lalu simpan ke cache & DB.
    Dipanggil via threading.Thread agar HTTP request bisa langsung return < 1 detik.

    articles diteruskan dari route agar tidak perlu fetch ulang ke Supabase.

    State:
      _INSIGHTS_GENERATING[period_key] = True       → sedang berjalan
      _INSIGHTS_GENERATING[period_key] = False      → selesai (hasil sudah di cache/DB)
      _INSIGHTS_GENERATING[period_key] = "error: ..." → gagal
    """
    import time as _time
    print(f"[AI Insights] Worker thread dimulai untuk {period_key} ({len(articles)} artikel).")
    try:
        insights = generate_insights(
            period_label    = period_label,
            date_from       = date_from,
            date_to         = date_to,
            supabase_client = supabase,
            articles        = articles,
        )

        _save_insight_to_db(period_key, period_label, insights, len(articles))

        payload = {
            "status":        "ok",
            "cached":        False,
            "quarter":       period_label,
            "article_count": len(articles),
            "data": {
                "pdrb":         insights["pdrb"],
                "kemiskinan":   insights["kemiskinan"],
                "pengangguran": insights["pengangguran"],
            },
            "sources": insights.get("sources", {}),
        }
        _INSIGHTS_CACHE[period_key] = {"ts": _time.time(), "data": payload}
        _INSIGHTS_GENERATING[period_key] = False
        print(f"[AI Insights] Worker selesai untuk {period_key}.")

    except Exception as exc:
        _INSIGHTS_GENERATING[period_key] = f"error: {exc}"
        print(f"[AI Insights] Worker error untuk {period_key}: {exc}")


@app.route("/api/ai-insights", methods=["GET"])
@login_required
@limiter.limit("30 per hour")
def get_ai_insights():
    """
    Hasilkan insight AI (DeepSeek) untuk PDRB, Kemiskinan, Pengangguran.

    Query params:
      period  — q1/q2/q3/q4/s1/s2/yearly (default: triwulan berjalan)
      year    — tahun (default: tahun berjalan)
      refresh — 1 untuk paksa regenerasi (bypass cache & DB)

    Response status:
      "ok"         → data baru selesai di-generate
      "generating" → background thread sedang berjalan, client harus poll ulang
      "error"      → thread terakhir gagal
    """
    period        = request.args.get("period", "").strip().lower()
    force_refresh = request.args.get("refresh", "") == "1"
    poll_request  = request.args.get("poll", "") == "1"
    year_str      = request.args.get("year", "").strip()
    year          = int(year_str) if year_str.isdigit() else None

    period_key, period_label, date_from, date_to = _get_period_range(period, year)

    # ── State generation ───────────────────────────────────────────────────────
    gen_state = _INSIGHTS_GENERATING.get(period_key)

    # Sumber utama hasil insight adalah DB (persisten antar restart/deploy)
    db_row = _load_insight_from_db(period_key)

    # Thread sebelumnya gagal — reset agar bisa dicoba ulang saat refresh
    if isinstance(gen_state, str) and gen_state.startswith("error"):
        error_msg = gen_state[len("error: "):]
        print(f"[AI Insights] Thread sebelumnya gagal untuk {period_key}: {error_msg}")
        return jsonify({
            "status":  "error",
            "message": f"Gagal menghasilkan insight: {error_msg}",
        }), 500

    # Request dari polling frontend: cek apakah hasil worker sudah siap
    if poll_request:
        if gen_state is True:
            print(f"[AI Insights] Poll: thread masih berjalan untuk {period_key}.")
            return jsonify({"status": "generating"})

        if db_row:
            print(f"[AI Insights] Poll: hasil DB siap untuk {period_key}.")
            return jsonify({
                "status":        "ok",
                "cached":        True,
                "quarter":       db_row["period_label"],
                "article_count": db_row["article_count"],
                "data": {
                    "pdrb":         db_row["pdrb"],
                    "kemiskinan":   db_row["kemiskinan"],
                    "pengangguran": db_row["pengangguran"],
                },
                "sources":      db_row["sources"],
                "generated_at": db_row["created_at"],
            })

        ready = _INSIGHTS_CACHE.get(period_key)
        if ready:
            print(f"[AI Insights] Poll: hasil siap untuk {period_key}.")
            return jsonify(ready["data"])

        print(f"[AI Insights] Poll: belum ada hasil untuk {period_key}.")
        return jsonify({"status": "generating"})

    # Request normal: jika DB sudah ada, selalu pakai DB (tidak overwrite hasil lama)
    if db_row:
        if force_refresh:
            print(f"[AI Insights] Refresh diabaikan karena data DB sudah ada untuk {period_key}.")
        else:
            print(f"[AI Insights] Ambil hasil dari DB untuk {period_key}.")
        return jsonify({
            "status":        "ok",
            "cached":        True,
            "quarter":       db_row["period_label"],
            "article_count": db_row["article_count"],
            "data": {
                "pdrb":         db_row["pdrb"],
                "kemiskinan":   db_row["kemiskinan"],
                "pengangguran": db_row["pengangguran"],
            },
            "sources":      db_row["sources"],
            "generated_at": db_row["created_at"],
        })

    # Request non-poll: DB belum ada → generate baru
    if gen_state is True:
        print(f"[AI Insights] Thread masih berjalan untuk {period_key} — return generating.")
        return jsonify({"status": "generating"})

    # Belum ada thread — fetch artikel terlebih dulu (cepat, < 2 detik)
    articles = _fetch_period_articles(date_from, date_to)

    # Jika tidak ada artikel untuk periode ini, return langsung tanpa spawn thread
    if not articles:
        print(f"[AI Insights] Tidak ada artikel untuk {period_key} — return langsung.")
        empty_payload = {
            "status":        "ok",
            "cached":        False,
            "quarter":       period_label,
            "article_count": 0,
            "data": {
                "pdrb":         "Belum ada data berita untuk periode ini.",
                "kemiskinan":   "Belum ada data berita untuk periode ini.",
                "pengangguran": "Belum ada data berita untuk periode ini.",
            },
            "sources": {"pdrb": [], "kemiskinan": [], "pengangguran": []},
        }
        _INSIGHTS_CACHE[period_key] = {"ts": 0.0, "data": empty_payload}
        return jsonify(empty_payload)

    # Ada artikel — spawn thread, pass articles agar tidak fetch ulang di worker
    _INSIGHTS_GENERATING[period_key] = True
    threading.Thread(
        target  = _generate_insights_worker,
        args    = (period_key, period_label, date_from, date_to, articles),
        daemon  = True,
        name    = f"ai-insights-{period_key}",
    ).start()
    print(f"[AI Insights] Thread spawned untuk {period_key} ({len(articles)} artikel) — return generating.")
    return jsonify({"status": "generating"})


# ── API: last scrape time ──────────────────────────────────────────────────────

@app.route("/api/last-scrape", methods=["GET"])
@login_required
def get_last_scrape():
    """
    Kembalikan:
      - last_scrape : timestamp terakhir scraping berjalan (dari scrape_log)
      - new_count   : jumlah berita yang masuk hari ini (sejak 00:00 WIB)
    """
    try:
        last_scrape = _fetch_last_scrape_timestamp()
        new_count   = _count_todays_articles()
        return jsonify({"status": "ok", "last_scrape": last_scrape, "new_count": new_count})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


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


# ── Scraping state ─────────────────────────────────────────────────────────────

_scraping_lock = threading.Lock()

_scrape_progress: dict = {
    "radartegal":   {"status": "idle", "scraped": 0, "inserted": 0, "message": "Menunggu..."},
    "panturapost":  {"status": "idle", "scraped": 0, "inserted": 0, "message": "Menunggu..."},
    "tribunjateng": {"status": "idle", "scraped": 0, "inserted": 0, "message": "Menunggu..."},
    "kompas":       {"status": "idle", "scraped": 0, "inserted": 0, "message": "Menunggu..."},
    "setdategal":   {"status": "idle", "scraped": 0, "inserted": 0, "message": "Menunggu..."},
}
_scrape_overall: dict = {"active": False, "done": False, "total_inserted": 0, "error": ""}


def _reset_progress():
    for key in _scrape_progress:
        _scrape_progress[key] = {"status": "idle", "scraped": 0, "inserted": 0, "message": "Menunggu..."}
    _scrape_overall.update({"active": True, "done": False, "total_inserted": 0, "error": ""})


@app.route("/api/scrape/progress", methods=["GET"])
@login_required
@limiter.exempt
def get_progress():
    return jsonify({"progress": _scrape_progress, "overall": _scrape_overall})


# ── Helpers: artikel ───────────────────────────────────────────────────────────

def _is_valid_article(article: dict | None, source_key: str) -> bool:
    """Return False kalau artikel harus dilewati (null, judul kosong, atau field NA)."""
    if not article or not article.get("title") or not article.get("url"):
        print(f"[SKIP] {source_key}: artikel null/judul kosong dilewati")
        return False

    if source_key == "tribunjateng":
        for field in ("title", "date", "content"):
            val = article.get(field, "")
            if not val or str(val).strip().upper() == "NA":
                print(f"[SKIP] {source_key}: field '{field}' kosong/NA — {article.get('url', '')}")
                return False

    return True


def _build_article_row(article: dict, source_label: str) -> dict:
    """Rakit dict row siap insert ke tabel berita."""
    normalized_date = normalize_date(article["date"])
    prediction_text = article.get("content") or article.get("title")
    kbli = predict_kbli_label(prediction_text, _kbli_predictor)
    return {
        "title":       article["title"],
        "date":        normalized_date,
        "date_parsed": parse_date_to_iso(normalized_date),
        "url":         article["url"],
        "content":     article["content"],
        "tags":        article["tags"].lower() if article.get("tags") else article.get("tags"),
        "kbli":        kbli,
        "source":      article.get("source") or source_label,
    }


def _insert_articles(articles: list, source_key: str) -> int:
    """
    Insert artikel valid ke Supabase, lalu generate embedding untuk artikel baru.
    Return jumlah yang berhasil diinsert.
    """
    source_label  = SOURCE_LABELS.get(source_key, source_key)
    inserted      = 0
    new_articles  = []   # kumpulkan artikel baru untuk di-embed setelah insert selesai

    for article in articles:
        if not _is_valid_article(article, source_key):
            continue
        try:
            row = _build_article_row(article, source_label)
            supabase.table("berita").insert(row).execute()
            inserted += 1
            new_articles.append({"url": row["url"], "article": article})
        except Exception as exc:
            print(f"[DB ERROR] {source_key}: {article.get('url', '')} — {exc}")

    _scrape_progress[source_key]["inserted"] = inserted

    # ── Generate embedding untuk artikel baru ────────────────────────────────
    # Dilakukan setelah insert agar insert tidak terhambat.
    # Jika embedding gagal, artikel tetap tersimpan (graceful degradation).
    if new_articles:
        embedded_count = 0
        for item in new_articles:
            try:
                embedding = embed_article(item["article"])
                if embedding:
                    supabase.table("berita").update(
                        {"embedding": embedding}
                    ).eq("url", item["url"]).execute()
                    embedded_count += 1
            except Exception as exc:
                print(f"[Embedding] Gagal embed artikel {item['url'][:60]}: {exc}")
        print(f"[Embedding] {source_key}: {embedded_count}/{len(new_articles)} artikel baru di-embed.")

    return inserted


def _run_kbli_backfill(batch_size: int = 100) -> int:
    """
    Prediksi KBLI untuk semua berita yang kbli-nya NULL.

    Opsi B — penanganan artikel yang tidak dapat diprediksi:
      - Prediksi return None + content DAN title keduanya kosong
        → set kbli = "—" agar tidak di-retry selamanya.
      - Prediksi return None + masih ada isi content/title
        → skip (akan dicoba lagi di backfill berikutnya).

    Return jumlah artikel yang berhasil diupdate.
    """
    if _kbli_predictor is None:
        print("[KBLI Backfill] Predictor tidak tersedia, backfill dilewati.")
        return 0

    total_updated = 0
    MAX_BATCHES   = 100   # batas keamanan agar tidak loop selamanya
    iteration     = 0

    print("[KBLI Backfill] Mulai memproses artikel tanpa KBLI...")

    while iteration < MAX_BATCHES:
        iteration += 1

        try:
            result = (
                supabase.table("berita")
                .select("id, title, content")
                .is_("kbli", "null")
                .limit(batch_size)
                .execute()
            )
        except Exception as exc:
            print(f"[KBLI Backfill] Gagal query DB (batch {iteration}): {exc}")
            break

        rows = result.data or []
        if not rows:
            break   # tidak ada lagi artikel tanpa KBLI

        updated_this_batch = 0

        for row in rows:
            content = (row.get("content") or "").strip()
            title   = (row.get("title")   or "").strip()
            prediction_text = content or title

            label = predict_kbli_label(prediction_text, _kbli_predictor)

            if label is None:
                # Opsi B: jika content DAN title benar-benar kosong,
                # tandai "—" agar tidak di-query ulang terus-menerus.
                if not content and not title:
                    label = "—"
                else:
                    # Prediksi gagal sementara (model error/exception),
                    # biarkan NULL dan coba lagi di run berikutnya.
                    continue

            try:
                supabase.table("berita").update({"kbli": label}).eq("id", row["id"]).execute()
                updated_this_batch += 1
                total_updated += 1
            except Exception as exc:
                print(f"[KBLI Backfill] Gagal update id={row['id']}: {exc}")

        # Anti-infinite-loop: hentikan jika satu batch penuh tidak ada yang terupdate.
        # Ini terjadi ketika semua artikel NULL yang tersisa memiliki content/title
        # tetapi model terus gagal memprediksinya (transient error).
        if updated_this_batch == 0:
            print(f"[KBLI Backfill] Batch {iteration} tidak ada update — menghentikan loop.")
            break

    print(f"[KBLI Backfill] Selesai. {total_updated} artikel diperbarui dalam {iteration} batch.")
    return total_updated


def _log_scrape_run(total_inserted: int):
    """Insert satu baris ke scrape_log. Gagal diam-diam agar tidak mengganggu flow."""
    try:
        supabase.table("scrape_log").insert({"total_inserted": total_inserted}).execute()
    except Exception as exc:
        print(f"[LOG] Gagal catat scrape_log: {exc}")


def _fetch_existing_urls() -> set:
    """Ambil semua URL berita dari DB untuk deduplikasi scraping."""
    result = supabase.table("berita").select("url").execute()
    return {row["url"] for row in result.data}


def _make_progress_callback(source_key: str):
    """Factory: buat callback progress untuk satu sumber berita."""
    def on_progress(count, msg=""):
        _scrape_progress[source_key]["scraped"] = count
        _scrape_progress[source_key]["message"] = msg or f"{count} berita ditemukan"
    return on_progress


def _run_scraper_source(
    key: str,
    scraper_fn,
    existing_urls: set,
    kwargs: dict,
) -> int:
    """Jalankan satu sumber scraper, update progress, dan insert hasilnya."""
    _scrape_progress[key]["status"]  = "running"
    _scrape_progress[key]["message"] = "Memulai scraping..."

    articles = scraper_fn(existing_urls, on_progress=_make_progress_callback(key), **kwargs)
    n = _insert_articles(articles, key)

    _scrape_progress[key]["status"]  = "done"
    _scrape_progress[key]["message"] = f"Selesai — {n} berita disimpan"
    print(f"[SCRAPE] {key}: {n} disimpan")
    return n


# ── Scraper config ─────────────────────────────────────────────────────────────

def _build_scraper_config(max_articles: int) -> list[tuple]:
    """Return daftar (key, scraper_fn, kwargs) untuk semua sumber."""
    max_pages = max(1, max_articles // 30)
    return [
        ("radartegal",   scrape_radartegal,   {"max_pages": max_pages}),
        ("panturapost",  scrape_panturapost,  {"max_articles": max_articles}),
        ("tribunjateng", scrape_tribunjateng, {"max_articles": max_articles}),
        ("kompas",       scrape_kompas,       {"max_articles": max_articles}),
        ("setdategal",   scrape_tegal,        {"max_articles": max_articles}),
    ]


# ── Worker thread ──────────────────────────────────────────────────────────────

def _scrape_worker(max_articles: int):
    try:
        existing_urls  = _fetch_existing_urls()
        print(f"[SCRAPE] {len(existing_urls)} URL sudah ada di database.")

        total_inserted = sum(
            _run_scraper_source(key, fn, existing_urls, kwargs)
            for key, fn, kwargs in _build_scraper_config(max_articles)
        )

        _scrape_overall["total_inserted"] = total_inserted
        _log_scrape_run(total_inserted)
        print(f"[SCRAPE] Semua selesai. Total {total_inserted} berita baru disimpan.")

        # Jalankan backfill KBLI setelah scraping selesai.
        # Menangani artikel baru yang mungkin masuk dengan kbli = NULL
        # (misalnya karena prediksi gagal sementara saat insert).
        if _kbli_predictor is not None:
            threading.Thread(
                target=_run_kbli_backfill,
                daemon=True,
                name="kbli-backfill-post-scrape",
            ).start()

    except Exception as exc:
        _scrape_overall["error"] = str(exc)
        print(f"[SCRAPE ERROR] {exc}")
        for key in _scrape_progress:
            if _scrape_progress[key]["status"] == "running":
                _scrape_progress[key].update({"status": "error", "message": f"Error: {exc}"})

    finally:
        _scrape_overall["active"] = False
        _scrape_overall["done"]   = True
        _scraping_lock.release()


# ── Synchronous scrape (untuk cron / Vercel serverless) ────────────────────────

def _scrape_sync(max_articles: int) -> dict:
    """Jalankan scraping secara synchronous. Cocok untuk Vercel serverless."""
    results        = {}
    total_inserted = 0
    errors         = []

    try:
        existing_urls = _fetch_existing_urls()
        print(f"[SCRAPE-SYNC] {len(existing_urls)} URL sudah ada di database.")
    except Exception as exc:
        return {"status": "error", "message": f"Gagal fetch existing URLs: {exc}"}

    for key, scraper_fn, kwargs in _build_scraper_config(max_articles):
        try:
            articles       = scraper_fn(existing_urls, **kwargs)
            n              = _insert_articles(articles, key)
            results[key]   = n
            total_inserted += n
            print(f"[SCRAPE-SYNC] {key}: {n} disimpan")
        except Exception as exc:
            errors.append(f"{key}: {exc}")
            print(f"[SCRAPE-SYNC ERROR] {key}: {exc}")

    print(f"[SCRAPE-SYNC] Selesai. Total {total_inserted} berita baru disimpan.")
    _log_scrape_run(total_inserted)

    # Backfill KBLI setelah scraping sync — dijalankan di thread agar tidak
    # menambah waktu respons cron (Vercel mungkin sudah dekat timeout).
    if _kbli_predictor is not None:
        threading.Thread(
            target=_run_kbli_backfill,
            daemon=True,
            name="kbli-backfill-post-scrape-sync",
        ).start()

    return {
        "status":         "ok",
        "total_inserted": total_inserted,
        "results":        results,
        "errors":         errors,
    }


# ── Helper: cek API-key auth ───────────────────────────────────────────────────

def _is_valid_api_key() -> bool:
    """Return True jika request membawa header Authorization: Bearer <CRON_SECRET> yang valid."""
    cron_secret = os.getenv("CRON_SECRET", "")
    if not cron_secret:
        return False
    return request.headers.get("Authorization", "") == f"Bearer {cron_secret}"


# ── API: jalankan scraping ─────────────────────────────────────────────────────

@app.route("/api/scrape", methods=["POST"])
def start_scrape():
    """
    Dual auth:
      1. Session (dashboard) → threaded, return langsung
      2. API key via header Authorization: Bearer <CRON_SECRET> → synchronous
    """
    is_api_key = _is_valid_api_key()
    is_session = current_user.is_authenticated

    if not is_api_key and not is_session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    if is_session and not is_api_key and current_user.role != "admin":
        return jsonify({"status": "error", "message": "Akses ditolak. Hanya admin yang dapat menjalankan scraping."}), 403

    body         = request.get_json(silent=True) or {}
    max_articles = max(1, min(int(body.get("max_articles", 150)), 999))

    if is_api_key:
        print(f"[SCRAPE] Dipanggil via API key — mode synchronous, maks {max_articles} artikel")
        result = _scrape_sync(max_articles)
        return jsonify(result), 200 if result.get("status") == "ok" else 500

    if not _scraping_lock.acquire(blocking=False):
        return jsonify({"status": "error", "message": "Scraping sedang berjalan, tunggu hingga selesai."}), 409

    _reset_progress()
    threading.Thread(target=_scrape_worker, args=(max_articles,), daemon=True).start()
    return jsonify({"status": "started", "max_articles": max_articles})


# ── API: backfill KBLI manual (admin only) ─────────────────────────────────────

@app.route("/api/admin/backfill-kbli", methods=["POST"])
@login_required
def api_backfill_kbli():
    """
    Trigger backfill prediksi KBLI untuk semua berita yang kbli-nya NULL.
    Admin only. Berjalan di background thread, return langsung.
    """
    if current_user.role != "admin":
        return jsonify({"status": "error", "message": "Akses ditolak. Hanya admin."}), 403

    if _kbli_predictor is None:
        return jsonify({
            "status":  "error",
            "message": "Model KBLI tidak tersedia. Periksa folder model_kbli/.",
        }), 503

    threading.Thread(
        target=_run_kbli_backfill,
        daemon=True,
        name="kbli-backfill-manual",
    ).start()
    return jsonify({"status": "started", "message": "Backfill KBLI dimulai di background."})


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

# Jalankan backfill KBLI saat startup — mengisi artikel lama yang kbli-nya NULL.
# Harus ditempatkan di sini (bukan di atas) karena _run_kbli_backfill
# baru terdefinisi setelah seluruh fungsi di atas dimuat.
if _kbli_predictor is not None:
    threading.Thread(
        target=_run_kbli_backfill,
        daemon=True,
        name="kbli-backfill-startup",
    ).start()

if __name__ == "__main__":
    print("=" * 50)
    print("Dashboard Berita — Flask Server (4 Sumber)")
    print("=" * 50)
    print(f"Supabase: {os.getenv('SUPABASE_URL')}")
    print("Buka http://localhost:5000")
    print()
    app.run(debug=True, port=5000, use_reloader=False)
