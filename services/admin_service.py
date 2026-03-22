"""
Service layer untuk fitur admin users.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from repositories.password_reset_codes import PasswordResetCodeRepository
from repositories.users import UserRepository
from utils.auth import USERNAME_ALLOWED, generate_auth_code, generate_temp_password


class AdminService:
    """Orkestrasi use-case admin tanpa ketergantungan ke Flask route."""

    def __init__(
        self,
        *,
        user_repository: UserRepository | None = None,
        reset_code_repository: PasswordResetCodeRepository | None = None,
        bcrypt_ext: Any = None,
    ):
        self._users = user_repository or UserRepository()
        self._codes = reset_code_repository or PasswordResetCodeRepository()
        if bcrypt_ext is not None:
            self._bcrypt = bcrypt_ext
        else:
            from config.extensions import bcrypt as default_bcrypt

            self._bcrypt = default_bcrypt

    def list_users(self) -> tuple[dict[str, Any], int]:
        try:
            users = self._users.list_users()
            now_iso = datetime.now(timezone.utc).isoformat()
            active_code_users = self._codes.list_active_code_user_ids(now_iso)

            for user in users:
                try:
                    raw_user_id = user.get("id")
                    user_id = int(str(raw_user_id)) if raw_user_id is not None else -1
                except Exception:
                    user_id = -1
                user["has_active_code"] = user_id in active_code_users

            return {"status": "ok", "data": users}, 200
        except Exception as exc:
            print(f"[ADMIN] Gagal ambil daftar user: {exc}")
            return {"status": "error", "message": "Gagal mengambil data pengguna."}, 500

    def create_user(self, username: str, actor_username: str) -> tuple[dict[str, Any], int]:
        if len(username) < 3:
            return {"status": "error", "message": "Username minimal 3 karakter."}, 400
        if not all(char in USERNAME_ALLOWED for char in username):
            return {
                "status": "error",
                "message": (
                    "Username hanya boleh mengandung huruf, angka, underscore (_), atau dash (-)."
                ),
            }, 400

        try:
            if self._users.username_exists(username):
                return {"status": "error", "message": "Username sudah digunakan."}, 409
        except Exception as exc:
            print(f"[ADMIN] Gagal cek duplikat username: {exc}")
            return {"status": "error", "message": "Gagal memvalidasi username."}, 500

        temp_password = generate_temp_password()
        password_hash = self._bcrypt.generate_password_hash(temp_password, rounds=12).decode("utf-8")

        try:
            new_user = self._users.create_user(
                username=username,
                password_hash=password_hash,
                role="user",
                must_change_password=True,
            )
        except Exception as exc:
            print(f"[ADMIN] Gagal buat user: {exc}")
            return {"status": "error", "message": "Gagal membuat pengguna."}, 500

        if not new_user:
            return {"status": "error", "message": "Gagal membuat pengguna."}, 500

        print(f"[ADMIN] User baru dibuat: {username} (oleh {actor_username})")
        return {
            "status": "ok",
            "user": {
                "id": new_user.get("id"),
                "username": username,
                "role": "user",
                "must_change_password": True,
                "created_at": new_user.get("created_at"),
            },
            "generated_password": temp_password,
        }, 201

    def delete_user(
        self,
        *,
        user_id: int,
        actor_user_id: int | str,
        actor_username: str,
    ) -> tuple[dict[str, Any], int]:
        if str(user_id) == str(actor_user_id):
            return {"status": "error", "message": "Tidak dapat menghapus akun sendiri."}, 400

        try:
            target = self._users.get_user_by_id(user_id)
            if not target:
                return {"status": "error", "message": "Pengguna tidak ditemukan."}, 404

            target_username = str(target.get("username") or "")
            self._codes.delete_codes_by_user_id(user_id)
            self._users.delete_user(user_id)
        except Exception as exc:
            print(f"[ADMIN] Gagal hapus user {user_id}: {exc}")
            return {"status": "error", "message": "Gagal menghapus pengguna."}, 500

        print(f"[ADMIN] User dihapus: {target_username} (oleh {actor_username})")
        return {
            "status": "ok",
            "message": f"Pengguna '{target_username}' berhasil dihapus.",
        }, 200

    def generate_user_auth_code(
        self,
        *,
        user_id: int,
        actor_username: str,
    ) -> tuple[dict[str, Any], int]:
        try:
            target = self._users.get_user_by_id(user_id)
            if not target:
                return {"status": "error", "message": "Pengguna tidak ditemukan."}, 404
            target_username = str(target.get("username") or "")
        except Exception as exc:
            print(f"[ADMIN] Gagal verifikasi user {user_id}: {exc}")
            return {"status": "error", "message": "Gagal memvalidasi pengguna."}, 500

        try:
            self._codes.delete_codes_by_user_id(user_id)
        except Exception as exc:
            print(f"[ADMIN] Gagal hapus kode lama user {user_id}: {exc}")

        code_plain, code_hash = generate_auth_code()
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        try:
            self._codes.create_code(user_id, code_hash, expires_at.isoformat())
        except Exception as exc:
            print(f"[ADMIN] Gagal simpan kode reset user {user_id}: {exc}")
            return {"status": "error", "message": "Gagal menyimpan kode autentikasi."}, 500

        print(f"[ADMIN] Kode reset dibuat untuk user: {target_username} (oleh {actor_username})")
        return {
            "status": "ok",
            "username": target_username,
            "code": code_plain,
            "expires_at": expires_at.strftime("%d %b %Y, %H:%M WIB"),
        }, 200
