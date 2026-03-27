from schemas.berita import BeritaFilterQuery
from services.berita_service import BeritaService


class _FakeBeritaRepository:
    def list_berita(self, **_kwargs):
        return {
            "data": [{"id": 1, "title": "A"}, {"id": 2, "title": "B"}],
            "total_items": 32,
        }

    def export_berita(self, **_kwargs):
        return [{"id": 10, "title": "Export"}]

    def list_dashboard_summary_rows(self, _cutoff):
        return [
            {
                "id": 1,
                "date": "10 Maret 2026, 10:00 WIB",
                "date_parsed": "2026-03-10",
                "tags": "Inflasi | Pangan",
                "kbli": "C/Industri",
            },
            {
                "id": 2,
                "date": "09 Maret 2026, 10:00 WIB",
                "date_parsed": "2026-03-09",
                "tags": "Pangan",
                "kbli": "C/Industri",
            },
        ]

    def list_filter_option_rows(self):
        return [
            {
                "kbli": "A/Pertanian",
                "aktivitas_ekonomi": "1/Kondisi umum",
                "pdrb_pengeluaran": "PKRT-01/Makanan dan minuman tidak beralkohol",
            },
            {
                "kbli": "Tidak Relevan",
                "aktivitas_ekonomi": "—",
                "pdrb_pengeluaran": "—",
            },
            {
                "kbli": "C/Industri",
                "aktivitas_ekonomi": "9/Industri makanan",
                "pdrb_pengeluaran": "PMTB-01/Bangunan dan Tempat Tinggal",
            },
        ]

    def list_year_rows(self):
        return [
            {"date_parsed": "2024-12-01"},
            {"date_parsed": "2026-01-15"},
            {"date_parsed": "2025-02-10"},
        ]

    def get_berita_by_id(self, berita_id: int):
        if berita_id == 1:
            return {"id": 1, "title": "Satu"}
        return None


def test_list_berita_generates_pagination_block():
    service = BeritaService(berita_repository=_FakeBeritaRepository())
    query = BeritaFilterQuery(
        search="",
        date_from="",
        date_to="",
        kbli_code="",
        aktivitas_code="",
        page=2,
        per_page=15,
        sort_by="date_parsed",
        sort_dir="desc",
    )

    result = service.list_berita(query)

    assert result["status"] == "ok"
    assert result["pagination"]["page"] == 2
    assert result["pagination"]["total_items"] == 32
    assert result["pagination"]["total_pages"] == 3
    assert result["pagination"]["has_prev"] is True
    assert result["pagination"]["has_next"] is True


def test_filter_options_extract_codes_and_sort_numerically():
    service = BeritaService(berita_repository=_FakeBeritaRepository())

    result = service.get_dashboard_data_filter_options()

    assert result["status"] == "ok"
    assert result["data"]["kbli_codes"] == ["A", "C"]
    assert result["data"]["aktivitas_codes"] == ["1", "9"]
    assert result["data"]["pdrb_pengeluaran_codes"] == ["PKRT-01", "PMTB-01"]


def test_get_berita_years_sorted_descending():
    service = BeritaService(berita_repository=_FakeBeritaRepository())

    result = service.get_berita_years()

    assert result == {"status": "ok", "years": ["2026", "2025", "2024"]}
