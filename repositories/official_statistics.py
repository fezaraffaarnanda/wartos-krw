"""Repository snapshot statistik resmi BPS."""

from __future__ import annotations

from typing import Any

from repositories.base import BaseRepository


class OfficialStatisticsRepository(BaseRepository):
    """Akses snapshot statistik resmi BPS di Supabase."""

    def load_year_snapshots(self, year: int) -> dict[str, dict[str, Any]]:
        try:
            result = (
                self._supabase.table("official_statistics_snapshots")
                .select(
                    "dataset_key, period_key, year, title, source, "
                    "updated_at_source_text, normalized_payload, fetched_at"
                )
                .eq("year", int(year))
                .execute()
            )
        except Exception as exc:
            print(f"[BPS] Gagal membaca snapshot statistik resmi dari DB: {exc}")
            return {}

        snapshots: dict[str, dict[str, Any]] = {}
        for row in result.data or []:
            dataset_key = str(row.get("dataset_key") or "").strip()
            payload = row.get("normalized_payload") or {}
            if not dataset_key or not isinstance(payload, dict):
                continue
            snapshots[dataset_key] = payload
        return snapshots

    def upsert_snapshots(self, snapshots: list[dict[str, Any]]) -> None:
        if not snapshots:
            return

        try:
            (
                self._supabase.table("official_statistics_snapshots")
                .upsert(snapshots, on_conflict="dataset_key,year,period_key")
                .execute()
            )
        except Exception as exc:
            print(f"[BPS] Gagal menyimpan snapshot statistik resmi ke DB: {exc}")


def load_official_statistics_year_snapshots(year: int) -> dict[str, dict[str, Any]]:
    return OfficialStatisticsRepository().load_year_snapshots(year)


def upsert_official_statistics_snapshots(snapshots: list[dict[str, Any]]) -> None:
    OfficialStatisticsRepository().upsert_snapshots(snapshots)
