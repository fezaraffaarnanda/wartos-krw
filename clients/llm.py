"""
llm_client.py — Centralized LLM client builder untuk Chat dan Insights.

Provider LLM:
  Gemini 3.1 Flash-Lite Preview via Google AI OpenAI-compatible endpoint
  → Diaktifkan jika GEMINI_API_KEY tersedia

"""

from openai import OpenAI

from config.settings import get_settings

# ── Konfigurasi provider ───────────────────────────────────────────────────────

# Gemini — via Google AI OpenAI-compatible endpoint
_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
_GEMINI_MODEL    = "gemini-3.1-flash-lite-preview"


# ── Public API ─────────────────────────────────────────────────────────────────

def build_chat_client() -> tuple[OpenAI, str]:
    """
    Buat Gemini LLM client.

    Membutuhkan GEMINI_API_KEY di environment variables.
    Return (client, model_name).

    Pola pemakaian:
      client, model = build_chat_client()
      response = client.chat.completions.create(model=model, messages=[...])
    """
    settings = get_settings()
    gemini_key = str(settings.GEMINI_API_KEY or "").strip()
    if gemini_key:
        print(f"[LLM] Provider: Gemini ({_GEMINI_MODEL})")
        return (
            OpenAI(api_key=gemini_key, base_url=_GEMINI_BASE_URL),
            _GEMINI_MODEL,
        )

    raise ValueError(
        "Tidak ada LLM API key yang tersedia. "
        "Set GEMINI_API_KEY di .env."
    )
