from services.auth_service import AuthService


class _FakeBcrypt:
    def check_password_hash(self, hashed: str, plain: str) -> bool:
        return hashed == f"hash:{plain}"

    def generate_password_hash(self, plain: str, rounds: int = 12) -> bytes:  # noqa: ARG002
        return f"hash:{plain}".encode("utf-8")


class _FakeUserRepository:
    def __init__(self):
        self._users = {
            1: {
                "id": 1,
                "username": "admin",
                "role": "admin",
                "password_hash": "hash:lama123",
                "must_change_password": True,
            }
        }

    def get_user_by_id(self, user_id):
        return self._users.get(int(user_id))

    def get_user_auth_by_username(self, username: str):
        for user in self._users.values():
            if user["username"] == username:
                return user
        return None

    def get_user_password_by_id(self, user_id):
        user = self._users.get(int(user_id))
        if not user:
            return None
        return {
            "id": user["id"],
            "username": user["username"],
            "password_hash": user["password_hash"],
        }

    def get_user_basic_by_username(self, username: str):
        for user in self._users.values():
            if user["username"] == username:
                return {"id": user["id"], "username": user["username"]}
        return None

    def update_password(self, user_id, password_hash: str, must_change_password: bool):
        user = self._users[int(user_id)]
        user["password_hash"] = password_hash
        user["must_change_password"] = must_change_password


class _FakeResetCodeRepository:
    def __init__(self):
        self.used_ids = []

    def get_valid_code(self, user_id, code_hash, now_iso):  # noqa: ARG002
        if str(user_id) == "1" and code_hash:
            return {"id": 99, "expires_at": "2099-01-01T00:00:00+00:00"}
        return None

    def mark_code_used(self, code_id, used_at_iso):  # noqa: ARG002
        self.used_ids.append(code_id)


def test_authenticate_user_success_and_failure():
    service = AuthService(
        user_repository=_FakeUserRepository(),
        reset_code_repository=_FakeResetCodeRepository(),
        bcrypt_ext=_FakeBcrypt(),
    )

    ok_user = service.authenticate_user("admin", "lama123")
    bad_user = service.authenticate_user("admin", "salah")

    assert ok_user is not None
    assert ok_user["username"] == "admin"
    assert bad_user is None


def test_change_password_rejects_same_password():
    service = AuthService(
        user_repository=_FakeUserRepository(),
        reset_code_repository=_FakeResetCodeRepository(),
        bcrypt_ext=_FakeBcrypt(),
    )

    payload, status_code = service.change_password(1, "lama123")

    assert status_code == 400
    assert payload["status"] == "error"


def test_reset_password_updates_hash_and_marks_code_used():
    user_repo = _FakeUserRepository()
    code_repo = _FakeResetCodeRepository()
    service = AuthService(
        user_repository=user_repo,
        reset_code_repository=code_repo,
        bcrypt_ext=_FakeBcrypt(),
    )

    payload, status_code = service.reset_password("admin", "AB12CD34", "baru12345")

    assert status_code == 200
    assert payload["status"] == "ok"
    assert user_repo.get_user_password_by_id(1)["password_hash"] == "hash:baru12345"
    assert code_repo.used_ids == [99]
