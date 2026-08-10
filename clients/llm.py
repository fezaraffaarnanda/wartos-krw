"""
llm_client.py — Centralized LLM client builder untuk Chat, Insights, dan classifier.

Provider LLM:
  DeepSeek Chat via OpenAI-compatible endpoint → default
  Gemini 3.1 Flash-Lite Preview → alternatif

Provider aktif ditentukan oleh tabel llm_provider_settings (diubah dari /admin/llm),
dengan cache TTL supaya gak query DB tiap panggilan. Kalau DB gak bisa diakses atau
provider yang dipilih key-nya kosong, otomatis fallback ke provider yang key-nya
tersedia (DeepSeek diutamakan) — toggle yang salah tidak boleh bikin fitur LLM down.
"""

import time

from openai import OpenAI

from config.settings import get_settings

# ── Konfigurasi provider ───────────────────────────────────────────────────────

# DeepSeek — via OpenAI-compatible endpoint
_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
_DEEPSEEK_MODEL    = "deepseek-v4-flash"

# Gemini — via Google AI OpenAI-compatible endpoint
_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
_GEMINI_MODEL    = "gemini-3.1-flash-lite-preview"

_PROVIDERS = {
    "deepseek": (_DEEPSEEK_BASE_URL, _DEEPSEEK_MODEL),
    "gemini":   (_GEMINI_BASE_URL, _GEMINI_MODEL),
}

# Cache provider aktif dari DB (per proses; serverless cold start refresh sendiri)
_PROVIDER_CACHE_TTL = 300  # detik
_provider_cache: dict = {"provider": None, "fetched_at": 0.0}


# ── Helper internal ─────────────────────────────────────────────────────────────

def _get_configured_provider() -> str | None:
    """Ambil provider aktif dari DB dengan cache TTL. None kalau DB gagal/kosong."""
    now = time.time()
    if (
        _provider_cache["provider"] is not None
        and now - _provider_cache["fetched_at"] < _PROVIDER_CACHE_TTL
    ):
        return _provider_cache["provider"]

    try:
        from repositories.llm_settings import LlmSettingsRepository
        provider = LlmSettingsRepository().get_provider()
    except Exception as exc:
        print(f"[LLM] Gagal ambil provider dari DB: {exc}")
        provider = None

    _provider_cache.update({"provider": provider, "fetched_at": now})
    return provider


def invalidate_provider_cache() -> None:
    """Paksa reload provider dari DB pada panggilan berikutnya (dipakai setelah admin ubah setting)."""
    _provider_cache.update({"provider": None, "fetched_at": 0.0})


# ── Public API ─────────────────────────────────────────────────────────────────

def build_chat_client() -> tuple[OpenAI, str]:
    """
    Buat LLM client sesuai provider aktif.

    Return (client, model_name).

    Pola pemakaian:
      client, model = build_chat_client()
      response = client.chat.completions.create(model=model, messages=[...])
    """
    settings = get_settings()
    deepseek_key = str(settings.DEEPSEEK_API_KEY or "").strip()
    gemini_key   = str(settings.GEMINI_API_KEY or "").strip()
    available = {
        "deepseek": deepseek_key,
        "gemini":   gemini_key,
    }

    configured = _get_configured_provider()
    if configured in _PROVIDERS and available.get(configured):
        provider = configured
    else:
        if configured and not available.get(configured):
            print(f"[LLM] Provider terkonfigurasi '{configured}' tidak punya API key — fallback.")
        # Fallback: DeepSeek diutamakan, lalu Gemini
        provider = "deepseek" if deepseek_key else ("gemini" if gemini_key else None)

    if provider is None:
        raise ValueError(
            "Tidak ada LLM API key yang tersedia. "
            "Set DEEPSEEK_API_KEY atau GEMINI_API_KEY di .env."
        )

    base_url, model = _PROVIDERS[provider]
    print(f"[LLM] Provider: {provider} ({model})")
    client = OpenAI(api_key=available[provider], base_url=base_url)
    if provider == "deepseek":
        _disable_deepseek_thinking(client)
    return client, model


def _disable_deepseek_thinking(client: OpenAI) -> None:
    """
    deepseek-v4-flash adalah reasoning model: tanpa ini, dia nulis chain-of-thought
    penuh ke field reasoning_content dulu dan sering menghabiskan max_tokens sebelum
    sempat menulis jawaban akhir (content='', finish_reason='length') -- classifier
    butuh jawaban pendek langsung, bukan CoT. Di-patch di instance client, bukan
    ubah tiap call site, supaya semua 7+ fitur otomatis kena.
    """
    original_create = client.chat.completions.create

    def patched_create(*args, **kwargs):
        extra_body = {"thinking": {"type": "disabled"}, **(kwargs.pop("extra_body", None) or {})}
        return original_create(*args, extra_body=extra_body, **kwargs)

    client.chat.completions.create = patched_create


def log_usage(
    *,
    feature: str,
    provider: str,
    model: str,
    usage=None,
    latency_ms: float | None = None,
    success: bool = True,
    error: str | None = None,
) -> None:
    """
    Catat token usage satu panggilan LLM ke llm_usage_log. Best-effort — kegagalan
    logging tidak boleh menggagalkan fitur pemanggil.

    `usage` adalah objek `.usage` dari response OpenAI SDK (punya prompt_tokens/
    completion_tokens/total_tokens), boleh None kalau provider gak mengembalikannya
    (mis. sebagian endpoint streaming tanpa stream_options include_usage).
    """
    try:
        from repositories.llm_usage import LlmUsageRepository
        LlmUsageRepository().insert(
            feature=feature,
            provider=provider,
            model=model,
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
            total_tokens=getattr(usage, "total_tokens", None),
            latency_ms=int(latency_ms) if latency_ms is not None else None,
            success=success,
            error=error,
        )
    except Exception as exc:
        print(f"[LLM] Gagal catat usage ({feature}/{provider}): {exc}")


def provider_from_model(model: str) -> str:
    """Balik model_name → nama provider ('deepseek'/'gemini'/'unknown'), buat logging."""
    for provider, (_base_url, provider_model) in _PROVIDERS.items():
        if provider_model == model:
            return provider
    return "unknown"
