"""
Repository log token usage LLM (tabel llm_usage_log).
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from repositories.base import BaseRepository


class LlmUsageRepository(BaseRepository):
    """Insert log usage per panggilan LLM + ringkasan agregat untuk admin panel."""

    def insert(
        self,
        *,
        feature: str,
        provider: str,
        model: str,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        latency_ms: int | None = None,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        """Best-effort insert. Gagal insert tidak boleh menggagalkan fitur pemanggil."""
        try:
            self._supabase.table("llm_usage_log").insert({
                "feature":           feature,
                "provider":          provider,
                "model":             model,
                "prompt_tokens":     prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens":      total_tokens,
                "latency_ms":        latency_ms,
                "success":           success,
                "error":             (error or "")[:2000] or None,
            }).execute()
        except Exception as exc:
            print(f"[LlmUsage] Gagal catat usage ({feature}/{provider}): {exc}")

    def summary(self, days: int = 30) -> list[dict[str, Any]]:
        """
        Ringkasan agregat per (feature, provider) dalam N hari terakhir:
        request_count, success_count, total_tokens.
        """
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        try:
            result = (
                self._supabase.table("llm_usage_log")
                .select("feature, provider, model, total_tokens, success, created_at")
                .gte("created_at", since)
                .execute()
            )
            rows = result.data or []
        except Exception as exc:
            print(f"[LlmUsage] Gagal ambil ringkasan usage: {exc}")
            return []

        buckets: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {
            "request_count": 0,
            "success_count": 0,
            "total_tokens":  0,
            "model":         "",
        })
        for row in rows:
            key = (row.get("feature") or "unknown", row.get("provider") or "unknown")
            bucket = buckets[key]
            bucket["request_count"] += 1
            if row.get("success"):
                bucket["success_count"] += 1
            bucket["total_tokens"] += int(row.get("total_tokens") or 0)
            bucket["model"] = row.get("model") or bucket["model"]

        return [
            {"feature": feature, "provider": provider, **stats}
            for (feature, provider), stats in sorted(buckets.items())
        ]
