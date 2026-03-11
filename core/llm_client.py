"""
llm_client.py — Centralized LLM client builder untuk Chat dan Insights.

Strategi provider (urutan prioritas):
  1. Gemini 3.1 Flash-Lite Preview via Google AI OpenAI-compatible endpoint
     → Lebih cepat, hemat quota, cocok untuk streaming
     → Diaktifkan jika GEMINI_API_KEY tersedia
  2. DeepSeek Chat via DeepSeek API
     → Fallback jika GEMINI_API_KEY tidak ada atau kosong
     → Diaktifkan jika DEEPSEEK_API_KEY tersedia

Modul ini dipakai oleh core/rag_chat.py dan core/ai_insights.py.
Embedding (text-embedding-3-small) tetap pakai OpenAI langsung — lihat core/embeddings.py.
"""

import os

from openai import OpenAI

# ── Konfigurasi provider ───────────────────────────────────────────────────────

# Gemini — via Google AI OpenAI-compatible endpoint
# Model: gemini-3.1-flash-lite-preview
_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
_GEMINI_MODEL    = "gemini-3.1-flash-lite-preview"

# DeepSeek — fallback
_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
_DEEPSEEK_MODEL    = "deepseek-chat"


# ── Public API ─────────────────────────────────────────────────────────────────

def build_chat_client() -> tuple[OpenAI, str]:
    """
    Buat LLM client dengan prioritas Gemini → DeepSeek.

    Urutan:
      1. Jika GEMINI_API_KEY tersedia → pakai Gemini 2.0 Flash-Lite
      2. Jika DEEPSEEK_API_KEY tersedia → pakai DeepSeek Chat
      3. Jika keduanya tidak ada → raise ValueError

    Return (client, model_name).
    Caller menggunakan model_name saat memanggil client.chat.completions.create().

    Pola pemakaian:
      client, model = build_chat_client()
      response = client.chat.completions.create(model=model, messages=[...])
    """
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    if gemini_key:
        print(f"[LLM] Provider: Gemini ({_GEMINI_MODEL})")
        return (
            OpenAI(api_key=gemini_key, base_url=_GEMINI_BASE_URL),
            _GEMINI_MODEL,
        )

    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if deepseek_key:
        print(f"[LLM] GEMINI_API_KEY tidak tersedia — fallback ke DeepSeek ({_DEEPSEEK_MODEL})")
        return (
            OpenAI(api_key=deepseek_key, base_url=_DEEPSEEK_BASE_URL),
            _DEEPSEEK_MODEL,
        )

    raise ValueError(
        "Tidak ada LLM API key yang tersedia. "
        "Set GEMINI_API_KEY (Gemini) atau DEEPSEEK_API_KEY (DeepSeek) di .env."
    )
