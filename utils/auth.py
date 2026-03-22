"""
Utility autentikasi yang dipakai lintas route/service.
"""

import hashlib
import secrets
import string

USERNAME_ALLOWED = frozenset(string.ascii_letters + string.digits + "_-")


def generate_temp_password(length: int = 14) -> str:
    """Generate password sementara yang kuat."""
    upper = string.ascii_uppercase
    lower = string.ascii_lowercase
    digits = string.digits
    symbols = "!@#$%^&*"
    must_have = [
        secrets.choice(upper),
        secrets.choice(lower),
        secrets.choice(digits),
        secrets.choice(symbols),
    ]
    pool = upper + lower + digits + symbols
    rest = [secrets.choice(pool) for _ in range(length - len(must_have))]
    combined = must_have + rest
    secrets.SystemRandom().shuffle(combined)
    return "".join(combined)


def generate_auth_code() -> tuple[str, str]:
    """Generate kode autentikasi 8 karakter dan hash SHA256-nya."""
    alphabet = string.ascii_uppercase + string.digits
    code_plain = "".join(secrets.choice(alphabet) for _ in range(8))
    code_hash = hashlib.sha256(code_plain.encode("utf-8")).hexdigest()
    return code_plain, code_hash
