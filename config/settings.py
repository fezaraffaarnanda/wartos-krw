"""
Konfigurasi aplikasi,  diambil dari environment variables.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings konfigurasi aplikasi dari .env"""

    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    BPS_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    FLASK_SECRET_KEY: str = ""
    CRON_SECRET: str = ""
    BPS_API_KEY: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Ambil instance settings"""
    return Settings()
