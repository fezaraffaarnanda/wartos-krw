"""
Service layer untuk domain berita.
"""

from datetime import datetime, timedelta
from typing import Any

from repositories.berita import BeritaRepository
from schemas.berita import BeritaFilterQuery


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
            sort_col=sort_col,
            sort_desc=sort_desc,
            page=query.page,
            per_page=query.per_page,
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
            },
        }

    def export_berita(self, query: BeritaFilterQuery) -> dict[str, Any]:
        rows = self._repo.export_berita(
            search=query.search,
            date_from=query.date_from,
            date_to=query.date_to,
            kbli_code=query.kbli_code,
            aktivitas_code=query.aktivitas_code,
        )
        return {"status": "ok", "data": rows}

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

            tags = [
                tag.strip().replace("#", "")
                for tag in raw_tags.replace(",", "|").split("|")
                if tag.strip()
            ]
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

        return {
            "status": "ok",
            "data": {
                "kbli_codes": sorted(kbli_codes),
                "aktivitas_codes": sorted(aktivitas_codes, key=lambda x: int(x)),
            },
        }

    def get_berita_by_id(self, berita_id: int) -> dict[str, Any] | None:
        if berita_id <= 0:
            return None
        return self._repo.get_berita_by_id(berita_id)
