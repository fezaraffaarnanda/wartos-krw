"""
Blueprint: autentikasi — login, logout, ganti/reset password, model User.
"""

import hashlib
import secrets
import string
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, jsonify, redirect, request, url_for
from flask_login import (
    UserMixin, current_user,
    login_required, login_user, logout_user,
)

from clients.supabase import supabase
from config.extensions import bcrypt, limiter, login_manager

auth_bp = Blueprint("auth", __name__)

# ── Konstanta ───────────────────────────────────────────────────────────────

_USERNAME_ALLOWED = frozenset(string.ascii_letters + string.digits + "_-")


# ── User model ──────────────────────────────────────────────────────────────

class User(UserMixin):
    def __init__(self, user_id: str, username: str, role: str, must_change_password: bool = False):
        self.id                   = user_id
        self.username             = username
        self.role                 = role
        self.must_change_password = must_change_password


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    try:
        result = (
            supabase.table("users")
            .select("id, username, role, must_change_password")
            .eq("id", user_id)
            .single()
            .execute()
        )
        if result.data:
            d = result.data
            return User(
                str(d["id"]),
                d["username"],
                d["role"],
                bool(d.get("must_change_password", False)),
            )
    except Exception:
        pass
    return None


# ── Decorators ──────────────────────────────────────────────────────────────

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


# ── Before request hook ─────────────────────────────────────────────────────

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
        return jsonify({
            "status":  "error",
            "message": "Anda wajib mengganti password sebelum mengakses fitur lain.",
        }), 403

    return redirect(url_for("pages.serve_change_password"))


# ── Helper: generate credentials ────────────────────────────────────────────

def _generate_temp_password(length: int = 14) -> str:
    """
    Generate password sementara yang kuat:
    minimal 1 huruf besar, 1 huruf kecil, 1 angka, 1 simbol.
    """
    upper   = string.ascii_uppercase
    lower   = string.ascii_lowercase
    digits  = string.digits
    symbols = "!@#$%^&*"
    must_have = [
        secrets.choice(upper),
        secrets.choice(lower),
        secrets.choice(digits),
        secrets.choice(symbols),
    ]
    pool     = upper + lower + digits + symbols
    rest     = [secrets.choice(pool) for _ in range(length - len(must_have))]
    combined = must_have + rest
    secrets.SystemRandom().shuffle(combined)
    return "".join(combined)


def _generate_auth_code() -> tuple[str, str]:
    """
    Generate kode autentikasi 8 karakter (UPPERCASE + digit).
    Return: (kode_plain, sha256_hash)
    """
    alphabet   = string.ascii_uppercase + string.digits
    code_plain = "".join(secrets.choice(alphabet) for _ in range(8))
    code_hash  = hashlib.sha256(code_plain.encode("utf-8")).hexdigest()
    return code_plain, code_hash


# ── Routes ──────────────────────────────────────────────────────────────────

@auth_bp.route("/api/login", methods=["POST"])
@limiter.limit("5 per 15 minutes")
def api_login():
    data = request.get_json(silent=True) or {}

    username = str(data.get("username", "")).strip().lower()[:100]
    password = str(data.get("password", "")).strip()[:200]

    if not username or not password:
        return jsonify({"status": "error", "message": "Username dan password wajib diisi."}), 400

    try:
        result = (
            supabase.table("users")
            .select("id, username, password_hash, role, must_change_password")
            .eq("username", username)
            .single()
            .execute()
        )
        user_data = result.data
    except Exception:
        user_data = None

    if not user_data or not bcrypt.check_password_hash(user_data["password_hash"], password):
        return jsonify({"status": "error", "message": "Username atau password salah."}), 401

    must_change = bool(user_data.get("must_change_password", False))
    user = User(str(user_data["id"]), user_data["username"], user_data["role"], must_change)
    login_user(user, remember=False)

    return jsonify({
        "status":               "ok",
        "username":             user.username,
        "role":                 user.role,
        "must_change_password": must_change,
    })


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("pages.serve_login"))


@auth_bp.route("/api/me", methods=["GET"])
@login_required
def api_me():
    return jsonify({
        "status":               "ok",
        "username":             current_user.username,
        "role":                 current_user.role,
        "must_change_password": current_user.must_change_password,
    })


@auth_bp.route("/api/auth/change-password", methods=["POST"])
@login_required
def api_change_password():
    """
    Ganti password oleh user yang sedang login.
    Password baru tidak boleh sama dengan password lama.
    """
    body         = request.get_json(silent=True) or {}
    new_password = str(body.get("new_password", "")).strip()

    if len(new_password) < 8:
        return jsonify({"status": "error", "message": "Password baru minimal 8 karakter."}), 400
    if len(new_password) > 200:
        return jsonify({"status": "error", "message": "Password terlalu panjang."}), 400

    try:
        user_res = (
            supabase.table("users")
            .select("password_hash")
            .eq("id", current_user.id)
            .single()
            .execute()
        )
        if not user_res.data:
            return jsonify({"status": "error", "message": "Sesi tidak valid."}), 401
        old_hash = user_res.data["password_hash"]
    except Exception as exc:
        print(f"[AUTH] Gagal ambil hash lama user {current_user.id}: {exc}")
        return jsonify({"status": "error", "message": "Gagal memvalidasi password."}), 500

    if bcrypt.check_password_hash(old_hash, new_password):
        return jsonify({"status": "error", "message": "Password baru tidak boleh sama dengan password lama."}), 400

    new_hash = bcrypt.generate_password_hash(new_password, rounds=12).decode("utf-8")
    try:
        supabase.table("users").update({
            "password_hash":        new_hash,
            "must_change_password": False,
        }).eq("id", current_user.id).execute()
    except Exception as exc:
        print(f"[AUTH] Gagal update password user {current_user.id}: {exc}")
        return jsonify({"status": "error", "message": "Gagal menyimpan password baru."}), 500

    current_user.must_change_password = False
    print(f"[AUTH] Password diubah oleh user: {current_user.username}")
    return jsonify({"status": "ok", "message": "Password berhasil diubah."})


@auth_bp.route("/api/auth/reset-password", methods=["POST"])
@limiter.limit("5 per 15 minutes")
def api_reset_password():
    """
    Reset password menggunakan kode autentikasi dari admin.
    Endpoint publik, dilindungi rate limiter.
    """
    body         = request.get_json(silent=True) or {}
    username     = str(body.get("username",     "")).strip().lower()[:100]
    code_input   = str(body.get("code",         "")).strip().upper()[:8]
    new_password = str(body.get("new_password", "")).strip()

    if not username or not code_input or not new_password:
        return jsonify({"status": "error", "message": "Username, kode autentikasi, dan password baru wajib diisi."}), 400

    if len(new_password) < 8:
        return jsonify({"status": "error", "message": "Password baru minimal 8 karakter."}), 400
    if len(new_password) > 200:
        return jsonify({"status": "error", "message": "Password terlalu panjang."}), 400

    try:
        user_res = (
            supabase.table("users")
            .select("id, username")
            .eq("username", username)
            .single()
            .execute()
        )
        user_data = user_res.data
    except Exception:
        user_data = None

    _INVALID_MSG = "Username atau kode autentikasi tidak valid, atau kode sudah kedaluwarsa."

    if not user_data:
        return jsonify({"status": "error", "message": _INVALID_MSG}), 401

    user_id    = user_data["id"]
    code_hash  = hashlib.sha256(code_input.encode("utf-8")).hexdigest()
    now_iso    = datetime.now(timezone.utc).isoformat()

    try:
        code_res = (
            supabase.table("password_reset_codes")
            .select("id, expires_at")
            .eq("user_id",   user_id)
            .eq("code_hash", code_hash)
            .is_("used_at",  "null")
            .gt("expires_at", now_iso)
            .limit(1)
            .execute()
        )
        code_row = code_res.data[0] if code_res.data else None
    except Exception as exc:
        print(f"[AUTH] Gagal validasi kode reset untuk user {username}: {exc}")
        return jsonify({"status": "error", "message": "Gagal memvalidasi kode autentikasi."}), 500

    if not code_row:
        return jsonify({"status": "error", "message": _INVALID_MSG}), 401

    try:
        supabase.table("password_reset_codes").update({
            "used_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", code_row["id"]).execute()
    except Exception as exc:
        print(f"[AUTH] Gagal tandai kode reset terpakai (id={code_row['id']}): {exc}")

    new_hash = bcrypt.generate_password_hash(new_password, rounds=12).decode("utf-8")
    try:
        supabase.table("users").update({
            "password_hash":        new_hash,
            "must_change_password": False,
        }).eq("id", user_id).execute()
    except Exception as exc:
        print(f"[AUTH] Gagal update password via kode reset untuk user {username}: {exc}")
        return jsonify({"status": "error", "message": "Gagal menyimpan password baru."}), 500

    print(f"[AUTH] Password direset via kode autentikasi: {username}")
    return jsonify({"status": "ok", "message": "Password berhasil direset. Silakan login dengan password baru."})
