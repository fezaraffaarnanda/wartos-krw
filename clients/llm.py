"""
llm_client.py — Centralized LLM client builder untuk Chat, Insights, dan classifier.

Provider LLM:
  DeepSeek Chat via OpenAI-compatible endpoint → diaktifkan jika DEEPSEEK_API_KEY tersedia
  Gemini 3.1 Flash-Lite Preview → fallback jika GEMINI_API_KEY tersedia

"""

from openai import OpenAI

from config.settings import get_settings

# ── Konfigurasi provider ───────────────────────────────────────────────────────

# DeepSeek — via OpenAI-compatible endpoint
_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
_DEEPSEEK_MODEL    = "deepseek-v4-flash"

# Gemini — via Google AI OpenAI-compatible endpoint
_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
_GEMINI_MODEL    = "gemini-3.1-flash-lite-preview"


# ── Public API ─────────────────────────────────────────────────────────────────

def build_chat_client() -> tuple[OpenAI, str]:
    """
    Buat LLM client (DeepSeek diutamakan, fallback Gemini).

    Return (client, model_name).

    Pola pemakaian:
      client, model = build_chat_client()
      response = client.chat.completions.create(model=model, messages=[...])
    """
    settings = get_settings()

    deepseek_key = str(settings.DEEPSEEK_API_KEY or "").strip()
    if deepseek_key:
        print(f"[LLM] Provider: DeepSeek ({_DEEPSEEK_MODEL})")
        return (
            OpenAI(api_key=deepseek_key, base_url=_DEEPSEEK_BASE_URL),
            _DEEPSEEK_MODEL,
        )

    gemini_key = str(settings.GEMINI_API_KEY or "").strip()
    if gemini_key:
        print(f"[LLM] Provider: Gemini ({_GEMINI_MODEL})")
        return (
            OpenAI(api_key=gemini_key, base_url=_GEMINI_BASE_URL),
            _GEMINI_MODEL,
        )

    raise ValueError(
        "Tidak ada LLM API key yang tersedia. "
        "Set DEEPSEEK_API_KEY atau GEMINI_API_KEY di .env."
    )
