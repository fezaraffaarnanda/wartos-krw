"""
Service layer untuk domain berita.
"""

from datetime import datetime, timedelta
from typing import Any

from ai.aktivitas import AKTIVITAS_LABELS
from ai.kbli import format_kbli_hasil
from ai.pdrb_pengeluaran import (
    PDRB_PENGELUARAN_CODE_ORDER,
    format_pdrb_pengeluaran_hasil,
)
from repositories.berita import BeritaRepository
from schemas.berita import BeritaFilterQuery
from utils.tags import clean_tags, split_tags


class BeritaService:
    """Orkestrasi logic bisnis berita terpisah dari Flask route."""

    def __init__(self, berita_repository: BeritaRepository | None = None):
        self._repo = berita_repository or BeritaRepository()

    def list_berita(self, query: BeritaFilterQuery) -> dict[str, Any]:
        sort_col, sort_desc, sort_dir = query.resolve_sort()
        result = self._repo.list_berita(
            search=query.search,
            date_from=query.date_from,
            date_to=query.date_to,
            kbli_code=query.kbli_code,
            aktivitas_code=query.aktivitas_code,
            pdrb_pengeluaran_code=query.pdrb_pengeluaran_code,
            sort_col=sort_col,
            sort_desc=sort_desc,
            page=query.page,
            per_page=query.per_page,
            archive_status=query.archive_status,
        )

        total_items = int(result.get("total_items", 0))
        total_pages = max(1, (total_items + query.per_page - 1) // query.per_page)

        return {
            "status": "ok",
            "data": result.get("data", []),
            "pagination": {
                "page": query.page,
                "per_page": query.per_page,
                "total_items": total_items,
                "total_pages": total_pages,
                "has_prev": query.page > 1,
                "has_next": query.page < total_pages,
            },
            "filters": {
                "search": query.search,
                "date_from": query.date_from,
                "date_to": query.date_to,
                "sort_by": sort_col,
                "sort_dir": sort_dir,
                "kbli_code": query.kbli_code,
                "aktivitas_code": query.aktivitas_code,
                "pdrb_pengeluaran_code": query.pdrb_pengeluaran_code,
                "archive_status": query.archive_status,
            },
        }

    def export_berita(self, query: BeritaFilterQuery) -> dict[str, Any]:
        rows = self._repo.export_berita(
            search=query.search,
            date_from=query.date_from,
            date_to=query.date_to,
            kbli_code=query.kbli_code,
            aktivitas_code=query.aktivitas_code,
            pdrb_pengeluaran_code=query.pdrb_pengeluaran_code,
            archive_status=query.archive_status,
        )
        return {"status": "ok", "data": rows}

    def update_archive_status(self, berita_id: int, *, is_archived: bool) -> tuple[dict[str, Any], int]:
        if berita_id <= 0:
            return {"status": "error", "message": "ID berita tidak valid."}, 400

        berita = self._repo.get_berita_by_id(berita_id)
        if not berita:
            return {"status": "error", "message": "Berita tidak ditemukan."}, 404

        updated = self._repo.set_archive_status(berita_id, is_archived=is_archived)
        if not updated:
            return {"status": "error", "message": "Gagal memperbarui status arsip."}, 500

        action_label = "diarsipkan" if is_archived else "dipulihkan"
        return {
            "status": "ok",
            "message": f"Berita berhasil {action_label}.",
            "data": updated,
        }, 200

    def update_classification(
        self,
        berita_id: int,
        *,
        kbli_code: str,
        aktivitas_code: str,
        pdrb_pengeluaran_code: str,
    ) -> tuple[dict[str, Any], int]:
        if berita_id <= 0:
            return {"status": "error", "message": "ID berita tidak valid."}, 400

        berita = self._repo.get_berita_by_id(berita_id)
        if not berita:
            return {"status": "error", "message": "Berita tidak ditemukan."}, 404

        kbli_value = self._normalize_kbli_value(kbli_code)
        aktivitas_value = self._normalize_aktivitas_value(aktivitas_code)
        pdrb_pengeluaran_value = self._normalize_pdrb_pengeluaran_value(
            pdrb_pengeluaran_code
        )

        if kbli_value is None:
            return {"status": "error", "message": "Kode KBLI tidak valid."}, 400

        if aktivitas_value is None:
            return {"status": "error", "message": "Kode aktivitas ekonomi tidak valid."}, 400

        if pdrb_pengeluaran_value is None:
            return {"status": "error", "message": "Kode PDRB pengeluaran tidak valid."}, 400

        updated = self._repo.update_classification(
            berita_id,
            kbli=kbli_value,
            aktivitas_ekonomi=aktivitas_value,
            pdrb_pengeluaran=pdrb_pengeluaran_value,
        )
        if not updated:
            return {"status": "error", "message": "Gagal menyimpan klasifikasi."}, 500

        return {
            "status": "ok",
            "message": "Klasifikasi berita berhasil diperbarui.",
            "data": updated,
        }, 200

    def get_dashboard_overview_summary(self) -> dict[str, Any]:
        now = datetime.now()
        cutoff = (now - timedelta(days=30)).date().isoformat()
        month_prefix = now.strftime("%Y-%m")

        rows = self._repo.list_dashboard_summary_rows(cutoff)

        total_30d = len(rows)
        latest_date = rows[0].get("date") if rows else None

        kbli_count: dict[str, int] = {}
        tag_count: dict[str, int] = {}
        month_tag_count: dict[str, int] = {}

        for row in rows:
            raw_kbli = str(row.get("kbli") or "").strip()
            if raw_kbli and raw_kbli.lower() not in {"tidak relevan", "-", "—"}:
                kode = raw_kbli.split("/")[0].strip().upper()
                if kode:
                    kbli_count[kode] = kbli_count.get(kode, 0) + 1

            raw_tags = str(row.get("tags") or "").strip()
            if not raw_tags:
                continue

            # Baris lama (sebelum backfill pembersihan tag) masih bisa berisi
            # identitas sumber/pejabat — saring lagi di sini supaya KPI top-tags
            # tidak menunggu backfill selesai. clean_tags idempoten, jadi tidak
            # ada efek samping untuk baris yang sudah bersih.
            tags = split_tags(clean_tags(raw_tags))
            for tag in tags:
                key = tag.lower()
                tag_count[key] = tag_count.get(key, 0) + 1

                date_parsed = str(row.get("date_parsed") or "")
                if date_parsed.startswith(month_prefix):
                    month_tag_count[key] = month_tag_count.get(key, 0) + 1

        top_kbli = sorted(kbli_count.items(), key=lambda x: x[1], reverse=True)[:5]
        top_tags_30d = sorted(tag_count.items(), key=lambda x: x[1], reverse=True)[:5]
        top_tags_month = sorted(month_tag_count.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "status": "ok",
            "data": {
                "total_30d": total_30d,
                "latest_date": latest_date,
                "top_kbli": [{"code": code, "count": count} for code, count in top_kbli],
                "top_tags_30d": [{"tag": tag, "count": count} for tag, count in top_tags_30d],
                "top_tags_month": [
                    {"tag": tag, "count": count} for tag, count in top_tags_month
                ],
            },
        }

    def get_berita_years(self) -> dict[str, Any]:
        rows = self._repo.list_year_rows()
        years = sorted(
            {str(row.get("date_parsed"))[:4] for row in rows if row.get("date_parsed")},
            reverse=True,
        )
        return {"status": "ok", "years": years}

    def get_dashboard_data_filter_options(self) -> dict[str, Any]:
        rows = self._repo.list_filter_option_rows()

        kbli_codes: set[str] = set()
        aktivitas_codes: set[str] = set()
        pdrb_pengeluaran_codes: set[str] = set()

        for row in rows:
            raw_kbli = str(row.get("kbli") or "").strip()
            if raw_kbli and raw_kbli.lower() not in {"tidak relevan", "-", "—"}:
                code = raw_kbli.split("/")[0].strip().upper()
                if code:
                    kbli_codes.add(code)

            raw_aktivitas = str(row.get("aktivitas_ekonomi") or "").strip()
            if raw_aktivitas and raw_aktivitas not in {"-", "—"}:
                code = raw_aktivitas.split("/")[0].strip()
                if code.isdigit():
                    aktivitas_codes.add(code)

            raw_pdrb_pengeluaran = str(row.get("pdrb_pengeluaran") or "").strip()
            if raw_pdrb_pengeluaran and raw_pdrb_pengeluaran not in {"-", "—", "Tidak Relevan"}:
                code = raw_pdrb_pengeluaran.split("/")[0].strip().upper()
                if code:
                    pdrb_pengeluaran_codes.add(code)

        return {
            "status": "ok",
            "data": {
                "kbli_codes": sorted(kbli_codes),
                "aktivitas_codes": sorted(aktivitas_codes, key=lambda x: int(x)),
                "pdrb_pengeluaran_codes": sorted(
                    pdrb_pengeluaran_codes,
                    key=lambda x: PDRB_PENGELUARAN_CODE_ORDER.get(x, 9999),
                ),
            },
        }

    def get_berita_by_id(self, berita_id: int) -> dict[str, Any] | None:
        if berita_id <= 0:
            return None
        return self._repo.get_berita_by_id(berita_id)

    @staticmethod
    def _normalize_kbli_value(kbli_code: str) -> str | None:
        normalized = str(kbli_code or "").strip().upper()
        if not normalized:
            return None

        if normalized == "TIDAK RELEVAN":
            return "Tidak Relevan"

        formatted = format_kbli_hasil(normalized)
        return formatted if formatted and "/" in formatted else None

    @staticmethod
    def _normalize_aktivitas_value(aktivitas_code: str) -> str | None:
        normalized = str(aktivitas_code or "").strip()
        if not normalized:
            return None

        if normalized in {"-", "—"}:
            return "—"

        if normalized.lower() == "tidak relevan":
            return "Tidak Relevan"

        if not normalized.isdigit():
            return None

        nomor = int(normalized)
        label = AKTIVITAS_LABELS.get(nomor)
        if not label:
            return None

        return f"{nomor}/{label}"

    @staticmethod
    def _normalize_pdrb_pengeluaran_value(pdrb_pengeluaran_code: str) -> str | None:
        normalized = str(pdrb_pengeluaran_code or "").strip().upper()
        if not normalized:
            return None

        if normalized in {"-", "—"}:
            return "—"

        if normalized == "TIDAK RELEVAN":
            return "Tidak Relevan"

        formatted = format_pdrb_pengeluaran_hasil(normalized)
        return formatted if formatted and "/" in formatted else None
