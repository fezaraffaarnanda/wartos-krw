"""
Inisialisasi Supabase client
"""

from typing import Any

try:
    from supabase import create_client
except Exception:
    create_client = None

from config.settings import get_settings


class _MissingSupabaseClient:
    """Placeholder agar error konfigurasi lebih jelas."""

    def __getattr__(self, _name: str) -> Any:
        raise RuntimeError(
            "Supabase client belum terinisialisasi. "
            "Pastikan SUPABASE_URL dan SUPABASE_KEY tersedia di environment/.env."
        )


def _build_supabase_client() -> Any:
    settings = get_settings()
    supabase_url = str(settings.SUPABASE_URL or "").strip()
    supabase_key = str(settings.SUPABASE_KEY or "").strip()

    if not supabase_url or not supabase_key:
        print("[SUPABASE] SUPABASE_URL/SUPABASE_KEY belum diset.")
        return _MissingSupabaseClient()

    if create_client is None:
        print("[SUPABASE] Package 'supabase' belum terpasang di environment aktif.")
        return _MissingSupabaseClient()

    try:
        return create_client(supabase_url, supabase_key)
    except Exception as exc:
        print(f"[SUPABASE] Gagal inisialisasi client: {exc}")
        return _MissingSupabaseClient()


supabase = _build_supabase_client()
