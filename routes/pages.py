"""
Blueprint: halaman HTML.

Halaman yang memakai sidebar dirender lewat Jinja (`render_template`) supaya
menu datang dari satu partial `_sidebar.html` dan role dibaca di server --
bukan disalin ke tiap template lalu disembunyikan belakangan oleh JS.
Halaman tanpa sidebar (login, reset password) tetap file statis.
"""

from flask import Blueprint, redirect, render_template, send_from_directory, url_for
from flask_login import current_user, login_required

pages_bp = Blueprint("pages", __name__)


def _render_app_page(template: str):
    return render_template(template, is_admin=(current_user.role == "admin"))


def _admin_page(template: str):
    if current_user.role != "admin":
        return redirect(url_for("pages.dashboard"))
    return _render_app_page(template)


@pages_bp.route("/login")
def serve_login():
    if current_user.is_authenticated:
        return redirect(url_for("pages.index"))
    return send_from_directory("templates", "login.html")


@pages_bp.route("/")
def index():
    return redirect(url_for("pages.dashboard"))


@pages_bp.route("/dashboard")
@login_required
def dashboard():
    return _render_app_page("index.html")


@pages_bp.route("/berita/<int:berita_id>")
@login_required
def berita_detail(berita_id):
    return _render_app_page("berita.html")


@pages_bp.route("/admin/users")
@login_required
def serve_admin_users():
    return _admin_page("admin_users.html")


@pages_bp.route("/admin/relevance")
@login_required
def serve_admin_relevance():
    return _admin_page("admin_relevance.html")


@pages_bp.route("/admin/llm")
@login_required
def serve_admin_llm():
    return _admin_page("admin_llm.html")


@pages_bp.route("/admin/feedback")
@login_required
def serve_admin_feedback():
    return _admin_page("admin_feedback.html")


@pages_bp.route("/change-password")
@login_required
def serve_change_password():
    return send_from_directory("templates", "change_password.html")


@pages_bp.route("/reset-password")
def serve_reset_password():
    return send_from_directory("templates", "reset_password.html")


@pages_bp.route("/static/css/<path:filename>")
def serve_styles(filename):
    return send_from_directory("static/css", filename)


@pages_bp.route("/static/js/<path:filename>")
def serve_scripts(filename):
    return send_from_directory("static/js", filename)


@pages_bp.route("/static/bps.svg")
def serve_logo():
    return send_from_directory("static", "bps.svg")
