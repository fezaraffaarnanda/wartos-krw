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
        is_relevant: bool,
        username: str,
    ) -> dict[str, Any] | None:
        """Simpan label manual admin (ground truth) untuk berita."""
        try:
            result = (
                self._supabase.table("berita")
                .update({
                    "human_label":      is_relevant,
                    "human_labeled_at": datetime.now(timezone.utc).isoformat(),
                    "human_labeled_by": username,
                })
                .eq("id", berita_id)
                .execute()
            )
            rows = result.data or []
            return rows[0] if rows else None
        except Exception as exc:
            print(f"[BERITA] Gagal set human_label berita {berita_id}: {exc}")
            return None

    def list_relevance_review_rows(
        self,
        *,
        mode: str = "borderline",
        page: int = 1,
        per_page: int = 25,
    ) -> dict[str, Any]:
        """
        Antrian review classifier relevance.
          mode='borderline' : skor 40-59 (ragu)
          mode='unlabeled'  : human_label IS NULL
          mode='disagreement': human_label berbeda dgn is_relevant
          mode='all'        : semua yang sudah punya skor relevance
        """
        start = (page - 1) * per_page
        end = start + per_page - 1

        cols = (
            "id, title, url, source, date_parsed, "
            "is_relevant, relevance_score, relevance_reason, classifier_model, "
            "human_label, human_labeled_at, human_labeled_by"
        )
        query = (
            self._supabase.table("berita")
            .select(cols, count="exact")
            .order("relevance_score", desc=False, nullsfirst=False)
        )

        if mode == "disagreement":
            # Supabase tak bisa filter kolom vs kolom — ambil semua row berlabel,
            # filter + paginate di Python agar total_items akurat
            result = query.not_.is_("human_label", "null").execute()
            rows = [
                r for r in (result.data or [])
                if bool(r.get("human_label")) != bool(r.get("is_relevant"))
            ]
            return {"data": rows[start:end + 1], "total_items": len(rows)}

        if mode == "borderline":
            query = query.gte("relevance_score", 40).lte("relevance_score", 59)
        elif mode == "unlabeled":
            query = query.is_("human_label", "null").not_.is_("relevance_score", "null")
        else:  # all
            query = query.not_.is_("relevance_score", "null")

        result = query.range(start, end).execute()
        return {"data": result.data or [], "total_items": result.count or 0}

    def list_disagreement_export_rows(self, limit: int = 20) -> list[dict[str, Any]]:
        """
        Ambil kasus disagreement (mesin salah) untuk keperluan few-shot export.
        human_label IS NOT NULL dan human_label != is_relevant.
        Filter dilakukan di Python karena Supabase tidak bisa column vs column comparison.
        Urut relevance_score ASC — borderline error duluan (lebih informatif untuk prompt).
        """
        result = (
            self._supabase.table("berita")
            .select(
                "id, title, content, relevance_score, relevance_reason, "
                "is_relevant, human_label, source"
            )
            .not_.is_("human_label", "null")
            .not_.is_("relevance_score", "null")
            .order("relevance_score", desc=False, nullsfirst=False)
            .limit(limit * 3)  # ambil lebih banyak, nanti filter di Python
            .execute()
        )
        rows = result.data or []
        disagreements = [
            r for r in rows
            if r.get("human_label") is not None
            and bool(r.get("human_label")) != bool(r.get("is_relevant"))
        ]
        return disagreements[:limit]

    def relevance_confusion_rows(self) -> list[dict[str, Any]]:
        """Ambil semua row berlabel manusia untuk hitung precision/recall."""
        result = (
            self._supabase.table("berita")
            .select("is_relevant, human_label")
            .not_.is_("human_label", "null")
            .execute()
        )
        return result.data or []

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
