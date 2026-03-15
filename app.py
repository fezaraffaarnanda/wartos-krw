import os
import secrets
import threading
from datetime import timedelta

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, request, url_for

load_dotenv()

from extensions import bcrypt, limiter, login_manager
from routes.pages       import pages_bp
from routes.auth        import auth_bp, enforce_must_change_password
from routes.berita      import berita_bp
from routes.ai_insights import ai_insights_bp
from routes.ai_chat     import ai_chat_bp
from routes.scraping    import scraping_bp
from routes.admin       import admin_bp

from core.article_pipeline import set_classifiers, _run_kbli_backfill, _run_aktivitas_backfill, _run_embedding_backfill
from core.embeddings   import _build_embedding_client
from core.kbli_utils   import load_kbli_llm_classifier
from core.llm_client   import build_chat_client


# ── App factory ────────────────────────────────────────────────────────────

def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="/static", template_folder="templates")

    _secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
    if not os.getenv("FLASK_SECRET_KEY"):
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

    return app


app = create_app()


# ── Inisialisasi classifier KBLI ───────────────────────────────────────────

from core.db import supabase

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

set_classifiers(_kbli_predictor, _kbli_llm_client, _kbli_llm_model)


# ── Startup background threads ─────────────────────────────────────────────

if _kbli_predictor is not None:
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


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("Dashboard Berita — Flask Server (4 Sumber)")
    print("=" * 50)
    print(f"Supabase: {os.getenv('SUPABASE_URL')}")
    print("Buka http://localhost:5000")
    print()
    app.run(debug=True, port=5000, use_reloader=False)
