"""
Blueprint: halaman HTML statis.
Semua route di sini hanya menyajikan file HTML dari folder templates/.
"""

from flask import Blueprint, redirect, send_from_directory, url_for
from flask_login import current_user, login_required

pages_bp = Blueprint("pages", __name__)


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
    return send_from_directory("templates", "index.html")


@pages_bp.route("/berita/<int:berita_id>")
@login_required
def berita_detail(berita_id):
    return send_from_directory("templates", "berita.html")


@pages_bp.route("/admin/users")
@login_required
def serve_admin_users():
    if current_user.role != "admin":
        return redirect(url_for("pages.dashboard"))
    return send_from_directory("templates", "admin_users.html")


@pages_bp.route("/admin/relevance")
@login_required
def serve_admin_relevance():
    if current_user.role != "admin":
        return redirect(url_for("pages.dashboard"))
    return send_from_directory("templates", "admin_relevance.html")


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
