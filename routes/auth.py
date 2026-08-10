"""
Blueprint: autentikasi - login, logout, ganti/reset password, model User.
"""

from functools import wraps

from flask import Blueprint, jsonify, redirect, request, url_for
from flask_login import UserMixin, current_user, login_required, login_user, logout_user

from config.extensions import limiter, login_manager
from schemas.auth import ChangePasswordPayload, LoginPayload, ResetPasswordPayload
from services.auth_service import AuthService
from services.feedback_service import FeedbackService

auth_bp = Blueprint("auth", __name__)
_auth_service = AuthService()
_feedback_service = FeedbackService()


class User(UserMixin):
    def __init__(self, user_id: str, username: str, role: str, must_change_password: bool = False):
        self.id = user_id
        self.username = username
        self.role = role
        self.must_change_password = must_change_password


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    user_data = _auth_service.load_user(user_id)
    if not user_data:
        return None

    return User(
        str(user_data["id"]),
        user_data["username"],
        user_data["role"],
        bool(user_data.get("must_change_password", False)),
    )


def admin_required(f):
    """Decorator: memastikan user terautentikasi dan ber-role admin."""

    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            if request.path.startswith("/api/"):
                return jsonify({"status": "error", "message": "Sesi habis. Silakan login kembali."}), 401
            return redirect(url_for("pages.serve_login"))

        if current_user.role != "admin":
            if request.path.startswith("/api/"):
                return jsonify({"status": "error", "message": "Akses ditolak. Hanya admin."}), 403
            return redirect(url_for("pages.dashboard"))

        return f(*args, **kwargs)

    return decorated


def enforce_must_change_password():
    """
    Jika user ditandai must_change_password=True, blok akses ke halaman/API lain
    sampai password diganti.
    Didaftarkan ke app via app.before_request di app.py.
    """
    if not current_user.is_authenticated:
        return None

    if not getattr(current_user, "must_change_password", False):
        return None

    allowed_paths = {
        "/change-password",
        "/api/auth/change-password",
        "/api/me",
        "/logout",
    }

    if request.path.startswith("/static/"):
        return None

    if request.path in allowed_paths:
        return None

    if request.path.startswith("/api/"):
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Anda wajib mengganti password sebelum mengakses fitur lain.",
                }
            ),
            403,
        )

    return redirect(url_for("pages.serve_change_password"))


@auth_bp.route("/api/login", methods=["POST"])
@limiter.limit("5 per 15 minutes")
def api_login():
    body = request.get_json(silent=True) or {}
    payload = LoginPayload.from_body(body)

    if not payload.username or not payload.password:
        return jsonify({"status": "error", "message": "Username dan password wajib diisi."}), 400

    user_data = _auth_service.authenticate_user(payload.username, payload.password)
    if not user_data:
        return jsonify({"status": "error", "message": "Username atau password salah."}), 401

    must_change = bool(user_data.get("must_change_password", False))
    user = User(
        str(user_data["id"]),
        user_data["username"],
        user_data["role"],
        must_change,
    )
    login_user(user, remember=False)

    return jsonify(
        {
            "status": "ok",
            "username": user.username,
            "role": user.role,
            "must_change_password": must_change,
        }
    )


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("pages.serve_login"))


@auth_bp.route("/api/me", methods=["GET"])
@login_required
def api_me():
    feedback_prompt = _feedback_service.evaluate_prompt_state(user_id=int(current_user.id))
    return jsonify(
        {
            "status": "ok",
            "username": current_user.username,
            "role": current_user.role,
            "must_change_password": current_user.must_change_password,
            "feedback_prompt": feedback_prompt,
        }
    )


@auth_bp.route("/api/auth/change-password", methods=["POST"])
@login_required
def api_change_password():
    """
    Ganti password oleh user yang sedang login.
    Password baru tidak boleh sama dengan password lama.
    """
    body = request.get_json(silent=True) or {}
    payload = ChangePasswordPayload.from_body(body)
    new_password = payload.new_password

    if len(new_password) < 8:
        return jsonify({"status": "error", "message": "Password baru minimal 8 karakter."}), 400
    if len(new_password) > 200:
        return jsonify({"status": "error", "message": "Password terlalu panjang."}), 400

    response, status_code = _auth_service.change_password(current_user.id, new_password)
    if status_code == 200:
        current_user.must_change_password = False
        print(f"[AUTH] Password diubah oleh user: {current_user.username}")

    return jsonify(response), status_code


@auth_bp.route("/api/auth/reset-password", methods=["POST"])
@limiter.limit("5 per 15 minutes")
def api_reset_password():
    """
    Reset password menggunakan kode autentikasi dari admin.
    Endpoint publik, dilindungi rate limiter.
    """
    body = request.get_json(silent=True) or {}
    payload = ResetPasswordPayload.from_body(body)

    if not payload.username or not payload.code or not payload.new_password:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Username, kode autentikasi, dan password baru wajib diisi.",
                }
            ),
            400,
        )

    if len(payload.new_password) < 8:
        return jsonify({"status": "error", "message": "Password baru minimal 8 karakter."}), 400
    if len(payload.new_password) > 200:
        return jsonify({"status": "error", "message": "Password terlalu panjang."}), 400

    response, status_code = _auth_service.reset_password(
        payload.username,
        payload.code,
        payload.new_password,
    )
    if status_code == 200:
        print(f"[AUTH] Password direset via kode autentikasi: {payload.username}")

    return jsonify(response), status_code
