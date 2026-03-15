"""
Blueprint: manajemen user (admin only) — list, create, delete, generate auth code.
"""

import string
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from flask_login import current_user

from core.db import supabase
from extensions import bcrypt
from routes.auth import (
    admin_required,
    _USERNAME_ALLOWED,
    _generate_temp_password,
    _generate_auth_code,
)

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/api/admin/users", methods=["GET"])
@admin_required
def api_list_users():
    """Kembalikan daftar semua user beserta info kode reset aktif."""
    try:
        users_res = (
            supabase.table("users")
            .select("id, username, role, must_change_password, created_at")
            .order("created_at", desc=False)
            .execute()
        )
        users = users_res.data or []

        now_iso = datetime.now(timezone.utc).isoformat()
        codes_res = (
            supabase.table("password_reset_codes")
            .select("user_id, expires_at")
            .is_("used_at", "null")
            .gt("expires_at", now_iso)
            .execute()
        )
        active_code_users = {row["user_id"] for row in (codes_res.data or [])}

        for u in users:
            u["has_active_code"] = u["id"] in active_code_users

        return jsonify({"status": "ok", "data": users})
    except Exception as exc:
        print(f"[ADMIN] Gagal ambil daftar user: {exc}")
        return jsonify({"status": "error", "message": "Gagal mengambil data pengguna."}), 500


@admin_bp.route("/api/admin/users", methods=["POST"])
@admin_required
def api_create_user():
    """
    Buat user baru. Password di-generate otomatis dan dikembalikan sekali ke admin.
    User wajib ganti password saat pertama login.
    """
    body     = request.get_json(silent=True) or {}
    username = str(body.get("username", "")).strip().lower()[:50]

    if len(username) < 3:
        return jsonify({"status": "error", "message": "Username minimal 3 karakter."}), 400
    if not all(c in _USERNAME_ALLOWED for c in username):
        return jsonify({"status": "error", "message": "Username hanya boleh mengandung huruf, angka, underscore (_), atau dash (-)."}), 400

    try:
        existing = (
            supabase.table("users")
            .select("id")
            .eq("username", username)
            .execute()
        )
        if existing.data:
            return jsonify({"status": "error", "message": "Username sudah digunakan."}), 409
    except Exception as exc:
        print(f"[ADMIN] Gagal cek duplikat username: {exc}")
        return jsonify({"status": "error", "message": "Gagal memvalidasi username."}), 500

    temp_password = _generate_temp_password()
    pw_hash       = bcrypt.generate_password_hash(temp_password, rounds=12).decode("utf-8")

    try:
        result = (
            supabase.table("users")
            .insert({
                "username":             username,
                "password_hash":        pw_hash,
                "role":                 "user",
                "must_change_password": True,
            })
            .execute()
        )
        new_user = result.data[0] if result.data else {}
    except Exception as exc:
        print(f"[ADMIN] Gagal buat user: {exc}")
        return jsonify({"status": "error", "message": "Gagal membuat pengguna."}), 500

    print(f"[ADMIN] User baru dibuat: {username} (oleh {current_user.username})")
    return jsonify({
        "status": "ok",
        "user": {
            "id":                   new_user.get("id"),
            "username":             username,
            "role":                 "user",
            "must_change_password": True,
            "created_at":           new_user.get("created_at"),
        },
        "generated_password": temp_password,
    }), 201


@admin_bp.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
@admin_required
def api_delete_user(user_id: int):
    """Hapus user berdasarkan ID. Admin tidak dapat menghapus dirinya sendiri."""
    if str(user_id) == str(current_user.id):
        return jsonify({"status": "error", "message": "Tidak dapat menghapus akun sendiri."}), 400

    try:
        check = (
            supabase.table("users")
            .select("id, username")
            .eq("id", user_id)
            .single()
            .execute()
        )
        if not check.data:
            return jsonify({"status": "error", "message": "Pengguna tidak ditemukan."}), 404

        target_username = check.data["username"]

        supabase.table("password_reset_codes").delete().eq("user_id", user_id).execute()
        supabase.table("users").delete().eq("id", user_id).execute()

        print(f"[ADMIN] User dihapus: {target_username} (oleh {current_user.username})")
        return jsonify({"status": "ok", "message": f"Pengguna '{target_username}' berhasil dihapus."})
    except Exception as exc:
        print(f"[ADMIN] Gagal hapus user {user_id}: {exc}")
        return jsonify({"status": "error", "message": "Gagal menghapus pengguna."}), 500


@admin_bp.route("/api/admin/users/<int:user_id>/auth-code", methods=["POST"])
@admin_required
def api_generate_auth_code(user_id: int):
    """
    Generate kode autentikasi 8 karakter untuk reset password.
    Kode lama dihapus, kode baru berlaku 1 jam.
    """
    try:
        check = (
            supabase.table("users")
            .select("id, username")
            .eq("id", user_id)
            .single()
            .execute()
        )
        if not check.data:
            return jsonify({"status": "error", "message": "Pengguna tidak ditemukan."}), 404
        target_username = check.data["username"]
    except Exception as exc:
        print(f"[ADMIN] Gagal verifikasi user {user_id}: {exc}")
        return jsonify({"status": "error", "message": "Gagal memvalidasi pengguna."}), 500

    try:
        supabase.table("password_reset_codes").delete().eq("user_id", user_id).execute()
    except Exception as exc:
        print(f"[ADMIN] Gagal hapus kode lama user {user_id}: {exc}")

    code_plain, code_hash = _generate_auth_code()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    try:
        supabase.table("password_reset_codes").insert({
            "user_id":    user_id,
            "code_hash":  code_hash,
            "expires_at": expires_at.isoformat(),
        }).execute()
    except Exception as exc:
        print(f"[ADMIN] Gagal simpan kode reset user {user_id}: {exc}")
        return jsonify({"status": "error", "message": "Gagal menyimpan kode autentikasi."}), 500

    print(f"[ADMIN] Kode reset dibuat untuk user: {target_username} (oleh {current_user.username})")
    return jsonify({
        "status":     "ok",
        "username":   target_username,
        "code":       code_plain,
        "expires_at": expires_at.strftime("%d %b %Y, %H:%M WIB"),
    })
