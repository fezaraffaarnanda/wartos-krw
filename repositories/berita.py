"""
Repository berita.
"""

from datetime import datetime, timezone
from typing import Any

from config.region import FOCUS_AREA_SOURCES
from repositories.base import BaseRepository

# Supabase `.in_()` butuh list, bukan tuple.
_FOCUS_AREA_SOURCE_LIST = list(FOCUS_AREA_SOURCES)

BERITA_LIST_COLUMNS = (
    "id, title, date, date_parsed, url, tags, kbli, aktivitas_ekonomi, pdrb_pengeluaran, source, "
    "created_at, is_archived, archived_at"
)
BERITA_EXPORT_COLUMNS = (
    "id, title, date, date_parsed, url, tags, kbli, aktivitas_ekonomi, pdrb_pengeluaran, source, content, "
    "is_archived, archived_at"
)

RELEVANCE_QUEUE_COLUMNS = (
    "id, title, url, source, date_parsed, tags, "
    "is_relevant, relevance_score, relevance_uncertainty, relevance_reason, "
    "classifier_model, relevance_prompt_version, relevance_checked_at, relevance_attempts, "
    "human_label, human_labeled_at, human_labeled_by, label_source"
)
RELEVANCE_DETAIL_COLUMNS = RELEVANCE_QUEUE_COLUMNS + ", content, human_label_note"
_RELEVANCE_LABEL_FIELDS = (
    "id", "human_label", "human_labeled_at", "human_labeled_by", "label_source",
)
_RELEVANCE_SCORE_BANDS = (
    ("b00_19", 0, 19), ("b20_39", 20, 39), ("b40_59", 40, 59),
    ("b60_79", 60, 79), ("b80_100", 80, 100),
)


class BeritaRepository(BaseRepository):
    """Akses data berita dengan dukungan filtering dan pagination."""

    def list_berita(
        self,
        *,
        search: str,
        date_from: str,
        date_to: str,
        kbli_code: str,
        aktivitas_code: str,
        pdrb_pengeluaran_code: str,
        sort_col: str,
        sort_desc: bool,
        page: int,
        per_page: int,
        archive_status: str = "active",
    ) -> dict[str, Any]:
        start = (page - 1) * per_page
        end = start + per_page - 1

        query = (
            self._supabase.table("berita")
            .select(BERITA_LIST_COLUMNS, count="exact")
            .order(sort_col, desc=sort_desc, nullsfirst=False)
        )
        query = self._apply_filters(
            query,
            search=search,
            date_from=date_from,
            date_to=date_to,
            kbli_code=kbli_code,
            aktivitas_code=aktivitas_code,
            pdrb_pengeluaran_code=pdrb_pengeluaran_code,
            archive_status=archive_status,
        )
        result = query.range(start, end).execute()

        return {
            "data": result.data or [],
            "total_items": result.count or 0,
        }

    def export_berita(
        self,
        *,
        search: str,
        date_from: str,
        date_to: str,
        kbli_code: str,
        aktivitas_code: str,
        pdrb_pengeluaran_code: str,
        archive_status: str = "active",
    ) -> list[dict[str, Any]]:
        query = self._supabase.table("berita").select(BERITA_EXPORT_COLUMNS).order(
            "date_parsed", desc=True, nullsfirst=False
        )
        query = self._apply_filters(
            query,
            search=search,
            date_from=date_from,
            date_to=date_to,
            kbli_code=kbli_code,
            aktivitas_code=aktivitas_code,
            pdrb_pengeluaran_code=pdrb_pengeluaran_code,
            archive_status=archive_status,
        )
        result = query.execute()
        return result.data or []

    def set_archive_status(self, berita_id: int, *, is_archived: bool) -> dict[str, Any] | None:
        archived_at = datetime.now(timezone.utc).isoformat() if is_archived else None

        try:
            result = (
                self._supabase.table("berita")
                .update({
                    "is_archived": is_archived,
                    "archived_at": archived_at,
                })
                .eq("id", berita_id)
                .execute()
            )
            rows = result.data or []
            return rows[0] if rows else None
        except Exception as exc:
            print(f"[BERITA] Gagal update status arsip berita {berita_id}: {exc}")
            return None

    def update_classification(
        self,
        berita_id: int,
        *,
        kbli: str,
        aktivitas_ekonomi: str,
        pdrb_pengeluaran: str,
    ) -> dict[str, Any] | None:
        try:
            result = (
                self._supabase.table("berita")
                .update({
                    "kbli": kbli,
                    "aktivitas_ekonomi": aktivitas_ekonomi,
                    "pdrb_pengeluaran": pdrb_pengeluaran,
                })
                .eq("id", berita_id)
                .execute()
            )
            rows = result.data or []
            return rows[0] if rows else None
        except Exception as exc:
            print(f"[BERITA] Gagal update klasifikasi berita {berita_id}: {exc}")
            return None

    def set_human_label(
        self,
        berita_id: int,
        *,
        is_relevant: bool | None,
        username: str,
        label_source: str = "targeted",
        note: str = "",
    ) -> dict[str, Any] | None:
        """Simpan/hapus label manual admin (ground truth) untuk berita.

        is_relevant=None -> hapus label (undo). Return HANYA field label,
        bukan seluruh row (row lama berisi content penuh, boros bandwidth
        pada sprint labeling satu request per keystroke).
        """
        if is_relevant is None:
            update = {
                "human_label": None,
                "human_labeled_at": None,
                "human_labeled_by": None,
                "label_source": None,
                "human_label_note": None,
            }
        else:
            update = {
                "human_label": is_relevant,
                "human_labeled_at": datetime.now(timezone.utc).isoformat(),
                "human_labeled_by": username,
                "label_source": label_source,
                "human_label_note": note or None,
            }
        try:
            result = (
                self._supabase.table("berita")
                .update(update)
                .eq("id", berita_id)
                .execute()
            )
            rows = result.data or []
            if not rows:
                return None
            return {k: rows[0].get(k) for k in _RELEVANCE_LABEL_FIELDS}
        except Exception as exc:
            print(f"[BERITA] Gagal set human_label berita {berita_id}: {exc}")
            return None

    def bulk_set_human_label(
        self,
        berita_ids: list[int],
        *,
        is_relevant: bool,
        username: str,
        label_source: str = "targeted",
    ) -> tuple[int, list[int]]:
        """Label banyak berita sekaligus dengan keputusan yang sama.

        Return (jumlah_berhasil, id_yang_gagal).
        """
        if not berita_ids:
            return 0, []
        try:
            result = (
                self._supabase.table("berita")
                .update({
                    "human_label": is_relevant,
                    "human_labeled_at": datetime.now(timezone.utc).isoformat(),
                    "human_labeled_by": username,
                    "label_source": label_source,
                })
                .in_("id", berita_ids)
                .execute()
            )
            updated_ids = {row["id"] for row in (result.data or [])}
            failed = [i for i in berita_ids if i not in updated_ids]
            return len(updated_ids), failed
        except Exception as exc:
            print(f"[BERITA] Gagal bulk label {berita_ids}: {exc}")
            return 0, list(berita_ids)

    def list_relevance_review_rows(
        self,
        *,
        mode: str = "uncertainty",
        page: int = 1,
        per_page: int = 25,
        search: str = "",
        source: str = "",
        score_min: int | None = None,
        score_max: int | None = None,
        audit_berita_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """
        Antrian review classifier relevance.
          mode='uncertainty'  : belum berlabel, urut abs(skor-50) naik (paling meragukan dulu)
          mode='audit'        : item dari batch sampel audit terbuka yang belum dilabeli
                                 (audit_berita_ids WAJIB diisi caller dari RelevanceAuditRepository)
          mode='failed'       : belum pernah berhasil diklasifikasi (relevance_checked_at IS NULL)
          mode='labeled'      : semua yang sudah dilabeli manusia
          mode='disagreement' : mesin != manusia (filter di Python, kolom vs kolom)
          mode='all'          : seluruh korpus berskor
        """
        start = (page - 1) * per_page
        end = start + per_page - 1

        def _apply_common(query: Any) -> Any:
            if search:
                query = query.ilike("title", f"%{search}%")
            if source:
                query = query.eq("source", source)
            if score_min is not None:
                query = query.gte("relevance_score", score_min)
            if score_max is not None:
                query = query.lte("relevance_score", score_max)
            return query

        if mode == "disagreement":
            query = self._supabase.table("berita").select(RELEVANCE_QUEUE_COLUMNS)
            query = _apply_common(query).not_.is_("human_label", "null")
            result = query.execute()
            rows = [
                r for r in (result.data or [])
                if bool(r.get("human_label")) != bool(r.get("is_relevant"))
            ]
            return {"data": rows[start:end + 1], "total_items": len(rows)}

        if mode == "audit":
            ids = audit_berita_ids or []
            if not ids:
                return {"data": [], "total_items": 0}
            query = self._supabase.table("berita").select(RELEVANCE_QUEUE_COLUMNS, count="exact")
            query = _apply_common(query).in_("id", ids)
            result = query.order("relevance_uncertainty", desc=False, nullsfirst=False).range(start, end).execute()
            return {"data": result.data or [], "total_items": result.count or 0}

        query = self._supabase.table("berita").select(RELEVANCE_QUEUE_COLUMNS, count="exact")
        query = _apply_common(query)

        if mode == "failed":
            query = query.is_("relevance_checked_at", "null")
        elif mode == "labeled":
            query = query.not_.is_("human_label", "null")
        elif mode == "all":
            query = query.not_.is_("relevance_score", "null")
        else:  # uncertainty (default)
            query = query.is_("human_label", "null").not_.is_("relevance_score", "null")

        sort_col = "relevance_uncertainty" if mode in ("uncertainty",) else "relevance_score"
        result = query.order(sort_col, desc=False, nullsfirst=False).range(start, end).execute()
        return {"data": result.data or [], "total_items": result.count or 0}

    def get_relevance_item(self, berita_id: int) -> dict[str, Any] | None:
        """Detail satu item untuk panel review (termasuk content penuh)."""
        try:
            result = (
                self._supabase.table("berita")
                .select(RELEVANCE_DETAIL_COLUMNS)
                .eq("id", berita_id)
                .single()
                .execute()
            )
            return result.data
        except Exception:
            return None

    def apply_relevance_result(
        self,
        berita_id: int,
        *,
        score: int,
        is_relevant: bool,
        reason: str,
        classifier_model: str,
        prompt_version: str,
        attempts: int,
    ) -> bool:
        """Simpan hasil klasifikasi SUKSES: set skor + relevance_checked_at=now()."""
        try:
            self._supabase.table("berita").update({
                "relevance_score": score,
                "is_relevant": is_relevant,
                "relevance_reason": reason,
                "classifier_model": classifier_model,
                "relevance_prompt_version": prompt_version,
                "relevance_checked_at": datetime.now(timezone.utc).isoformat(),
                "relevance_attempts": attempts,
            }).eq("id", berita_id).execute()
            return True
        except Exception as exc:
            print(f"[BERITA] Gagal simpan hasil relevance berita {berita_id}: {exc}")
            return False

    def mark_relevance_attempt_failed(self, berita_id: int, *, attempts: int) -> bool:
        """Naikkan relevance_attempts, biarkan relevance_checked_at tetap NULL."""
        try:
            self._supabase.table("berita").update({
                "relevance_attempts": attempts,
            }).eq("id", berita_id).execute()
            return True
        except Exception as exc:
            print(f"[BERITA] Gagal tandai attempt gagal berita {berita_id}: {exc}")
            return False

    def list_unchecked_relevance_rows(
        self, *, limit: int = 50, max_attempts: int = 3,
    ) -> list[dict[str, Any]]:
        """Row yang belum pernah berhasil diklasifikasi. Predikat backfill yang baru
        (menggantikan `is_relevant IS NULL` lama yang tidak pernah menjaring baris
        fail-open, karena baris itu ditandai is_relevant=True tanpa skor)."""
        result = (
            self._supabase.table("berita")
            .select("id, title, content, relevance_attempts")
            .is_("relevance_checked_at", "null")
            .lt("relevance_attempts", max_attempts)
            .limit(limit)
            .execute()
        )
        return result.data or []

    def count_unchecked_relevance(self) -> int:
        """Jumlah row gagal klasifikasi (badge tab 'Gagal Diklasifikasi')."""
        result = (
            self._supabase.table("berita")
            .select("id", count="exact")
            .is_("relevance_checked_at", "null")
            .execute()
        )
        return result.count or 0

    def list_labeled_rows(
        self, *, limit: int = 1000, include_content: bool = False,
        label_source: str | None = None,
    ) -> list[dict[str, Any]]:
        """Semua row berlabel manusia, dipaginasi internal.

        Menggantikan list_disagreement_export_rows() lama — TIDAK lagi
        pre-slice limit*3 lalu filter di Python (itu yang membuat false
        positive skor tinggi tidak pernah terjangkau few-shot export).
        """
        cols = RELEVANCE_DETAIL_COLUMNS if include_content else RELEVANCE_QUEUE_COLUMNS
        rows: list[dict[str, Any]] = []
        page_size = 500
        start = 0
        while len(rows) < limit:
            query = (
                self._supabase.table("berita")
                .select(cols)
                .not_.is_("human_label", "null")
            )
            if label_source:
                query = query.eq("label_source", label_source)
            result = query.order("id").range(start, start + page_size - 1).execute()
            batch = result.data or []
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < page_size:
                break
            start += page_size
        return rows[:limit]

    def relevance_confusion_rows(
        self, *, label_source: str | None = None, prompt_version: str | None = None,
    ) -> list[dict[str, Any]]:
        """Row berlabel untuk confusion matrix, opsional difilter sumber label / versi prompt."""
        rows: list[dict[str, Any]] = []
        page_size = 1000
        start = 0
        while True:
            query = (
                self._supabase.table("berita")
                .select("is_relevant, human_label, relevance_score, label_source, relevance_prompt_version")
                .not_.is_("human_label", "null")
            )
            if label_source:
                query = query.eq("label_source", label_source)
            if prompt_version:
                query = query.eq("relevance_prompt_version", prompt_version)
            result = query.order("id").range(start, start + page_size - 1).execute()
            batch = result.data or []
            rows.extend(batch)
            if len(batch) < page_size:
                break
            start += page_size
        return rows

    def count_scored_by_band(self) -> dict[str, int]:
        """Populasi per band skor (0-19/20-39/40-59/60-79/80-100) untuk bobot
        strata metrik audit. Hanya baris aktif yang berskor."""
        counts = {band: 0 for band, _lo, _hi in _RELEVANCE_SCORE_BANDS}
        rows: list[dict[str, Any]] = []
        page_size = 1000
        start = 0
        while True:
            result = (
                self._supabase.table("berita")
                .select("relevance_score")
                .not_.is_("relevance_score", "null")
                .eq("is_archived", False)
                .order("id")
                .range(start, start + page_size - 1)
                .execute()
            )
            batch = result.data or []
            rows.extend(batch)
            if len(batch) < page_size:
                break
            start += page_size

        for row in rows:
            score = row.get("relevance_score")
            if score is None:
                continue
            for band, lo, hi in _RELEVANCE_SCORE_BANDS:
                if lo <= score <= hi:
                    counts[band] += 1
                    break
        return counts

    def get_berita_by_id(self, berita_id: int) -> dict[str, Any] | None:
        try:
            result = (
                self._supabase.table("berita")
                .select("*")
                .eq("id", berita_id)
                .single()
                .execute()
            )
            return result.data
        except Exception:
            return None

    def list_dashboard_summary_rows(self, cutoff: str) -> list[dict[str, Any]]:
        result = (
            self._supabase.table("berita")
            .select("id, date, date_parsed, tags, kbli")
            .in_("source", _FOCUS_AREA_SOURCE_LIST)
            .eq("is_archived", False)
            .gte("date_parsed", cutoff)
            .order("date_parsed", desc=True, nullsfirst=False)
            .execute()
        )
        return result.data or []

    def list_filter_option_rows(self) -> list[dict[str, Any]]:
        result = (
            self._supabase.table("berita")
            .select("kbli, aktivitas_ekonomi, pdrb_pengeluaran")
            .in_("source", _FOCUS_AREA_SOURCE_LIST)
            .eq("is_archived", False)
            .execute()
        )
        return result.data or []

    def list_year_rows(self) -> list[dict[str, Any]]:
        result = (
            self._supabase.table("berita")
            .select("date_parsed")
            .in_("source", _FOCUS_AREA_SOURCE_LIST)
            .eq("is_archived", False)
            .not_.is_("date_parsed", "null")
            .execute()
        )
        return result.data or []

    def fetch_existing_urls(self) -> set[str]:
        """Ambil semua URL berita, dipaginasi (PostgREST default limit 1000/request)."""
        urls: set[str] = set()
        page_size = 1000
        start = 0
        while True:
            result = (
                self._supabase.table("berita")
                .select("url")
                .range(start, start + page_size - 1)
                .execute()
            )
            rows = result.data or []
            urls.update(row["url"] for row in rows if row.get("url"))
            if len(rows) < page_size:
                break
            start += page_size
        return urls

    @staticmethod
    def _apply_filters(
        query: Any,
        *,
        search: str,
        date_from: str,
        date_to: str,
        kbli_code: str,
        aktivitas_code: str,
        pdrb_pengeluaran_code: str,
        archive_status: str,
    ) -> Any:
        # Batasi ke sumber berita wilayah fokus. Berita warisan wilayah lama
        # tetap tersimpan di DB, tapi tidak ditampilkan maupun diekspor.
        query = query.in_("source", _FOCUS_AREA_SOURCE_LIST)

        if archive_status == "archived":
            query = query.eq("is_archived", True)
        elif archive_status == "relevant":
            # aktif + bukan tidak-relevan + KBLI terisi kategori nyata.
            # NOT IN dgn nilai NULL → NULL → row ter-exclude, jadi otomatis
            # berarti "kolom terisi DAN bukan placeholder".
            query = (
                query.eq("is_archived", False)
                .not_.eq("is_relevant", False)
                .not_.in_("kbli", ["—", "Tidak Relevan"])
            )
        elif archive_status != "all":
            query = query.eq("is_archived", False)

        if search:
            query = query.or_(
                f"title.ilike.%{search}%,tags.ilike.%{search}%,kbli.ilike.%{search}%,pdrb_pengeluaran.ilike.%{search}%"
            )
        if date_from:
            query = query.gte("date_parsed", date_from)
        if date_to:
            query = query.lte("date_parsed", date_to)
        if kbli_code:
            query = query.ilike("kbli", f"{kbli_code}/%")
        if aktivitas_code:
            query = query.ilike("aktivitas_ekonomi", f"{aktivitas_code}/%")
        if pdrb_pengeluaran_code:
            query = query.ilike("pdrb_pengeluaran", f"{pdrb_pengeluaran_code}/%")
        return query


def _fetch_existing_urls() -> set[str]:
    """Ambil semua URL berita dari DB untuk deduplikasi scraping."""
    return BeritaRepository().fetch_existing_urls()
