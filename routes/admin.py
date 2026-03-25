"""
Blueprint: manajemen user (admin only) - list, create, delete, generate auth code.
"""

from flask import Blueprint, jsonify, request
from flask_login import current_user

from routes.auth import admin_required
from schemas.admin import CreateUsersPayload
from services.admin_service import AdminService

admin_bp = Blueprint("admin", __name__)
_admin_service = AdminService()


@admin_bp.route("/api/admin/users", methods=["GET"])
@admin_required
def api_list_users():
    """Kembalikan daftar semua user beserta info kode reset aktif."""
    payload, status_code = _admin_service.list_users()
    return jsonify(payload), status_code


@admin_bp.route("/api/admin/users", methods=["POST"])
@admin_required
def api_create_user():
    """
    Buat user baru. Password di-generate otomatis dan dikembalikan sekali ke admin.
    User wajib ganti password saat pertama login.
    """
    body = request.get_json(silent=True) or {}
    data = CreateUsersPayload.from_body(body)

    payload, status_code = _admin_service.create_users(
        usernames=data.usernames,
        actor_username=current_user.username,
    )
    return jsonify(payload), status_code


@admin_bp.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
@admin_required
def api_delete_user(user_id: int):
    """Hapus user berdasarkan ID. Admin tidak dapat menghapus dirinya sendiri."""
    payload, status_code = _admin_service.delete_user(
        user_id=user_id,
        actor_user_id=current_user.id,
        actor_username=current_user.username,
    )
    return jsonify(payload), status_code


@admin_bp.route("/api/admin/users/<int:user_id>/auth-code", methods=["POST"])
@admin_required
def api_generate_auth_code(user_id: int):
    """
    Generate kode autentikasi 8 karakter untuk reset password.
    Kode lama dihapus, kode baru berlaku 1 jam.
    """
    payload, status_code = _admin_service.generate_user_auth_code(
        user_id=user_id,
        actor_username=current_user.username,
    )
    return jsonify(payload), status_code
