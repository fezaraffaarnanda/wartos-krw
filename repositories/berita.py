"""
Repository berita.
"""

from datetime import datetime, timezone
from typing import Any

from repositories.base import BaseRepository

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
            .eq("is_archived", False)
            .execute()
        )
        return result.data or []

    def list_year_rows(self) -> list[dict[str, Any]]:
        result = (
            self._supabase.table("berita")
            .select("date_parsed")
            .eq("is_archived", False)
            .not_.is_("date_parsed", "null")
            .execute()
        )
        return result.data or []

    def fetch_existing_urls(self) -> set[str]:
        result = self._supabase.table("berita").select("url").execute()
        return {row["url"] for row in (result.data or []) if row.get("url")}

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
        if archive_status == "archived":
            query = query.eq("is_archived", True)
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
