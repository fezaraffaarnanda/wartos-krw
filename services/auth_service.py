"""
Service layer autentikasi.
"""

import hashlib
from datetime import datetime, timezone
from typing import Any

from repositories.password_reset_codes import PasswordResetCodeRepository
from repositories.users import UserRepository


class AuthService:
    """Orkestrasi login, ganti password, dan reset password."""

    _INVALID_RESET_MSG = "Username atau kode autentikasi tidak valid, atau kode sudah kedaluwarsa."

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

    def load_user(self, user_id: int | str) -> dict[str, Any] | None:
        return self._users.get_user_by_id(user_id)

    def authenticate_user(self, username: str, password: str) -> dict[str, Any] | None:
        user_data = self._users.get_user_auth_by_username(username)
        if not user_data:
            return None

        password_hash = user_data.get("password_hash")
        if not password_hash:
            return None
        if not self._bcrypt.check_password_hash(password_hash, password):
            return None

        return {
            "id": user_data["id"],
            "username": user_data["username"],
            "role": user_data["role"],
            "must_change_password": bool(user_data.get("must_change_password", False)),
        }

    def change_password(self, user_id: int | str, new_password: str) -> tuple[dict[str, Any], int]:
        user_row = self._users.get_user_password_by_id(user_id)
        if not user_row:
            return {"status": "error", "message": "Sesi tidak valid."}, 401

        old_hash = user_row.get("password_hash")
        if not old_hash:
            return {"status": "error", "message": "Gagal memvalidasi password."}, 500

        if self._bcrypt.check_password_hash(old_hash, new_password):
            return {
                "status": "error",
                "message": "Password baru tidak boleh sama dengan password lama.",
            }, 400

        new_hash = self._bcrypt.generate_password_hash(new_password, rounds=12).decode("utf-8")
        try:
            self._users.update_password(user_id, new_hash, must_change_password=False)
        except Exception as exc:
            print(f"[AUTH] Gagal update password user {user_id}: {exc}")
            return {"status": "error", "message": "Gagal menyimpan password baru."}, 500

        return {"status": "ok", "message": "Password berhasil diubah."}, 200

    def reset_password(self, username: str, code_input: str, new_password: str) -> tuple[dict[str, Any], int]:
        user_data = self._users.get_user_basic_by_username(username)
        if not user_data:
            return {"status": "error", "message": self._INVALID_RESET_MSG}, 401

        user_id = user_data["id"]
        code_hash = hashlib.sha256(code_input.encode("utf-8")).hexdigest()
        now_iso = datetime.now(timezone.utc).isoformat()

        try:
            code_row = self._codes.get_valid_code(user_id, code_hash, now_iso)
        except Exception as exc:
            print(f"[AUTH] Gagal validasi kode reset untuk user {username}: {exc}")
            return {"status": "error", "message": "Gagal memvalidasi kode autentikasi."}, 500

        if not code_row:
            return {"status": "error", "message": self._INVALID_RESET_MSG}, 401

        try:
            self._codes.mark_code_used(
                code_id=code_row["id"],
                used_at_iso=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as exc:
            print(f"[AUTH] Gagal tandai kode reset terpakai (id={code_row['id']}): {exc}")

        new_hash = self._bcrypt.generate_password_hash(new_password, rounds=12).decode("utf-8")
        try:
            self._users.update_password(user_id, new_hash, must_change_password=False)
        except Exception as exc:
            print(f"[AUTH] Gagal update password via kode reset untuk user {username}: {exc}")
            return {"status": "error", "message": "Gagal menyimpan password baru."}, 500

        return {
            "status": "ok",
            "message": "Password berhasil direset. Silakan login dengan password baru.",
        }, 200
