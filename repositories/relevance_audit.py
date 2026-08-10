"""
Repository sampel audit acak berstrata classifier relevance
(tabel relevance_audit_batches, relevance_audit_items).
"""

from datetime import datetime, timezone
from typing import Any

from repositories.base import BaseRepository


class RelevanceAuditRepository(BaseRepository):
    """Akses batch sampel audit — satu-satunya sumber metrik precision/recall tak bias."""

    def draw_sample(self, *, batch_key: str, per_band: int, created_by: str) -> int | None:
        """Panggil RPC draw_relevance_audit_sample → return batch_id baru."""
        try:
            result = self._supabase.rpc("draw_relevance_audit_sample", {
                "p_batch_key": batch_key,
                "p_per_band": per_band,
                "p_created_by": created_by,
            }).execute()
            data = result.data
            if isinstance(data, list):
                return data[0] if data else None
            return data
        except Exception as exc:
            print(f"[RelevanceAudit] Gagal tarik sampel {batch_key}: {exc}")
            return None

    def get_open_batch(self) -> dict[str, Any] | None:
        try:
            result = (
                self._supabase.table("relevance_audit_batches")
                .select("*")
                .eq("status", "open")
                .order("id", desc=True)
                .limit(1)
                .execute()
            )
            rows = result.data or []
            return rows[0] if rows else None
        except Exception as exc:
            print(f"[RelevanceAudit] Gagal ambil batch terbuka: {exc}")
            return None

    def list_batch_item_ids(self, batch_id: int, *, unlabeled_only: bool = True) -> list[int]:
        try:
            query = (
                self._supabase.table("relevance_audit_items")
                .select("berita_id")
                .eq("batch_id", batch_id)
            )
            if unlabeled_only:
                query = query.is_("labeled_at", "null")
            result = query.execute()
            return [row["berita_id"] for row in (result.data or [])]
        except Exception as exc:
            print(f"[RelevanceAudit] Gagal list item batch {batch_id}: {exc}")
            return []

    def mark_item_labeled(self, *, batch_id: int, berita_id: int) -> bool:
        try:
            self._supabase.table("relevance_audit_items").update({
                "labeled_at": datetime.now(timezone.utc).isoformat(),
            }).eq("batch_id", batch_id).eq("berita_id", berita_id).execute()
            return True
        except Exception as exc:
            print(f"[RelevanceAudit] Gagal tandai item labeled batch={batch_id} berita={berita_id}: {exc}")
            return False

    def batch_progress(self, batch_id: int) -> dict[str, Any]:
        try:
            result = (
                self._supabase.table("relevance_audit_items")
                .select("labeled_at, band")
                .eq("batch_id", batch_id)
                .execute()
            )
            rows = result.data or []
        except Exception as exc:
            print(f"[RelevanceAudit] Gagal ambil progres batch {batch_id}: {exc}")
            rows = []

        total = len(rows)
        labeled = sum(1 for r in rows if r.get("labeled_at"))
        by_band: dict[str, dict[str, int]] = {}
        for row in rows:
            band = row.get("band") or "unknown"
            entry = by_band.setdefault(band, {"total": 0, "labeled": 0})
            entry["total"] += 1
            if row.get("labeled_at"):
                entry["labeled"] += 1

        return {"total": total, "labeled": labeled, "by_band": by_band}

    def close_batch(self, batch_id: int) -> bool:
        try:
            self._supabase.table("relevance_audit_batches").update({
                "status": "closed",
                "closed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", batch_id).execute()
            return True
        except Exception as exc:
            print(f"[RelevanceAudit] Gagal tutup batch {batch_id}: {exc}")
            return False
