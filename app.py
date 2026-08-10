import secrets
import threading
from datetime import timedelta

from flask import Flask, jsonify, redirect, request, url_for
from pydantic import ValidationError

from config.extensions import bcrypt, limiter, login_manager
from config.settings import get_settings
from routes.pages       import pages_bp
from routes.auth        import auth_bp, enforce_must_change_password
from routes.berita      import berita_bp
from routes.ai_insights import ai_insights_bp
from routes.ai_chat     import ai_chat_bp
from routes.official_statistics import official_statistics_bp
from routes.scraping    import scraping_bp
from routes.admin       import admin_bp

from services.article_pipeline import (
    set_classifiers,
    _run_relevance_backfill,
    _run_kbli_backfill,
    _run_aktivitas_backfill,
    _run_embedding_backfill,
    _run_pdrb_pengeluaran_backfill,
)
from ai.embeddings import _build_embedding_client
from ai.kbli import load_kbli_llm_classifier
from ai.pdrb_pengeluaran import load_pdrb_pengeluaran_llm_classifier
from clients.llm import build_chat_client


# ── App factory ────────────────────────────────────────────────────────────

def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="/static", template_folder="templates")

    settings = get_settings()
    configured_secret = str(settings.FLASK_SECRET_KEY or "").strip()

    _secret_key = configured_secret or secrets.token_hex(32)
    if not configured_secret:
        print("[PERINGATAN] FLASK_SECRET_KEY tidak ditemukan di .env — menggunakan kunci acak sementara.")

    app.secret_key = _secret_key
    app.config["SESSION_COOKIE_HTTPONLY"]     = True
    app.config["SESSION_COOKIE_SAMESITE"]    = "Lax"
    app.config["SESSION_COOKIE_SECURE"]      = False   # ubah True jika pakai HTTPS
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=1)

    bcrypt.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app)

    app.register_blueprint(pages_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(berita_bp)
    app.register_blueprint(ai_insights_bp)
    app.register_blueprint(ai_chat_bp)
    app.register_blueprint(official_statistics_bp)
    app.register_blueprint(scraping_bp)
    app.register_blueprint(admin_bp)

    app.before_request(enforce_must_change_password)

    # ── Error handlers ──────────────────────────────────────────────────────
    @app.errorhandler(401)
    def unauthorized(e):
        if request.path.startswith("/api/"):
            return jsonify({"status": "error", "message": "Sesi habis. Silakan login kembali."}), 401
        return redirect(url_for("pages.serve_login"))

    @app.errorhandler(403)
    def forbidden(e):
        return jsonify({"status": "error", "message": "Akses ditolak."}), 403

    @app.errorhandler(429)
    def rate_limit_exceeded(e):
        return jsonify({"status": "error", "message": "Terlalu banyak percobaan. Coba lagi dalam beberapa menit."}), 429

    @app.errorhandler(ValidationError)
    def invalid_payload(e: ValidationError):
        """Schema payload/query (schemas/*.py) memvalidasi lewat pydantic. Tanpa
        handler ini, input tidak valid yang lolos ke model_validate() jadi 500
        mentah alih-alih 400 -- kebanyakan schema mengklem/mem-whitelist input
        di classmethod from_body/from_request_args sebelum validasi sehingga
        jarang kena, tapi field dengan constraint langsung atas input pengguna
        (pattern, min_length, dst -- lihat schemas/relevance.py) tetap bisa
        memicu ValidationError."""
        first = e.errors()[0] if e.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", ())) or "field"
        return jsonify({"status": "error", "message": f"Input tidak valid pada '{field}': {first.get('msg', 'format salah')}."}), 400

    return app


app = create_app()


# ── Inisialisasi classifier KBLI ───────────────────────────────────────────

from clients.supabase import supabase

_kbli_embed_client = None
try:
    _kbli_embed_client = _build_embedding_client()
except Exception as _exc:
    print(f"[KBLI] Gagal buat embedding client untuk classifier: {_exc}")

_kbli_llm_client = None
_kbli_llm_model  = ""
try:
    _kbli_llm_client, _kbli_llm_model = build_chat_client()
except Exception as _exc:
    print(f"[KBLI] Gagal buat LLM client untuk classifier: {_exc}")

_kbli_predictor = load_kbli_llm_classifier(
    supabase, _kbli_embed_client, _kbli_llm_client, _kbli_llm_model
)

_pdrb_pengeluaran_predictor = load_pdrb_pengeluaran_llm_classifier(
    supabase, _kbli_embed_client, _kbli_llm_client, _kbli_llm_model
)

set_classifiers(
    _kbli_predictor,
    _kbli_llm_client,
    _kbli_llm_model,
    _pdrb_pengeluaran_predictor,
    relevance_llm_client=_kbli_llm_client,
    relevance_llm_model=_kbli_llm_model,
)


# ── Startup background threads ─────────────────────────────────────────────

if _kbli_llm_client is not None:
    def _relevance_then_kbli_startup():
        _run_relevance_backfill()
        if _kbli_predictor is not None:
            _run_kbli_backfill()

    threading.Thread(
        target=_relevance_then_kbli_startup,
        daemon=True,
        name="relevance-kbli-backfill-startup",
    ).start()
elif _kbli_predictor is not None:
    threading.Thread(
        target=_run_kbli_backfill,
        daemon=True,
        name="kbli-backfill-startup",
    ).start()

threading.Thread(
    target=_run_embedding_backfill,
    daemon=True,
    name="embedding-backfill-startup",
).start()

if _kbli_llm_client is not None:
    threading.Thread(
        target=_run_aktivitas_backfill,
        daemon=True,
        name="aktivitas-backfill-startup",
    ).start()

if _pdrb_pengeluaran_predictor is not None:
    threading.Thread(
        target=_run_pdrb_pengeluaran_backfill,
        daemon=True,
        name="pdrb-pengeluaran-backfill-startup",
    ).start()


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("WARTOS (Warta Online Statistik)")
    print("=" * 50)
    app.run(debug=True, port=5000, use_reloader=False)
