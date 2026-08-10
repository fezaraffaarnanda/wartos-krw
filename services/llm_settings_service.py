"""
Service layer untuk pengaturan provider LLM default (Gemini/DeepSeek) dan ringkasan usage.
"""

from __future__ import annotations

from typing import Any

from config.settings import get_settings
from repositories.llm_settings import LlmSettingsRepository
from repositories.llm_usage import LlmUsageRepository

_VALID_PROVIDERS = ("deepseek", "gemini")


class LlmSettingsService:
    """Use-case toggle provider LLM default + ringkasan usage, lepas dari Flask route."""

    def __init__(
        self,
        settings_repository: LlmSettingsRepository | None = None,
        usage_repository: LlmUsageRepository | None = None,
    ):
        self._settings = settings_repository or LlmSettingsRepository()
        self._usage = usage_repository or LlmUsageRepository()

    def _key_availability(self) -> dict[str, bool]:
        settings = get_settings()
        return {
            "deepseek": bool(str(settings.DEEPSEEK_API_KEY or "").strip()),
            "gemini":   bool(str(settings.GEMINI_API_KEY or "").strip()),
        }

    def get_provider_info(self) -> tuple[dict[str, Any], int]:
        provider = self._settings.get_provider() or "deepseek"
        return {
            "status":          "ok",
            "provider":        provider,
            "key_available":   self._key_availability(),
        }, 200

    def set_provider(self, provider: str, actor_username: str) -> tuple[dict[str, Any], int]:
        provider = (provider or "").strip().lower()
        if provider not in _VALID_PROVIDERS:
            return {
                "status": "error",
                "message": f"Provider harus salah satu dari {_VALID_PROVIDERS}.",
            }, 400

        row = self._settings.set_provider(provider, updated_by=actor_username)
        if row is None:
            return {"status": "error", "message": "Gagal simpan provider ke DB."}, 500

        from clients.llm import invalidate_provider_cache
        invalidate_provider_cache()

        key_available = self._key_availability()
        warning = None
        if not key_available.get(provider):
            warning = (
                f"Provider '{provider}' dipilih tapi API key-nya belum di-set di .env — "
                "fitur LLM akan otomatis fallback ke provider lain sampai key diisi."
            )

        return {
            "status":        "ok",
            "provider":      provider,
            "key_available": key_available,
            "warning":       warning,
        }, 200

    def usage_summary(self, days: int = 30) -> tuple[dict[str, Any], int]:
        rows = self._usage.summary(days=days)
        return {"status": "ok", "days": days, "rows": rows}, 200
