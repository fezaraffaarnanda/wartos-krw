"""
Skrip CLI untuk membuat user baru di tabel Supabase 'users'.

Penggunaan:
    python create_user.py <username> <password> <role>

Contoh:
    python create_user.py admin admin123 admin
    python create_user.py viewer viewer123 user
"""

import sys
import os
from dotenv import load_dotenv
from flask_bcrypt import generate_password_hash
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL atau SUPABASE_KEY tidak ditemukan di .env")
    sys.exit(1)


def create_user(username: str, password: str, role: str = "user") -> None:
    if not username or not password:
        print("ERROR: Username dan password tidak boleh kosong.")
        sys.exit(1)

    role = role.strip().lower()
    if role not in ("admin", "user"):
        print(f"ERROR: Role harus 'admin' atau 'user', bukan '{role}'.")
        sys.exit(1)

    pw_hash = generate_password_hash(password, rounds=12).decode("utf-8")

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    try:
        supabase.table("users").insert({
            "username":      username,
            "password_hash": pw_hash,
            "role":          role,
        }).execute()
        print(f"User '{username}' (role: {role}) berhasil dibuat.")
    except Exception as exc:
        print(f"ERROR menyimpan user: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    _username = sys.argv[1]
    _password = sys.argv[2]
    _role     = sys.argv[3] if len(sys.argv) > 3 else "user"

    create_user(_username, _password, _role)
