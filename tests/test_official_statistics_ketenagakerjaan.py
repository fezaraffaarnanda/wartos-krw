"""Tes normalizer seri ketenagakerjaan terhadap payload asli Web API BPS.

Fixture di `tests/fixtures/bps/` adalah respons apa adanya dari
`webapi.bps.go.id/v1/api/list/model/data` domain 3215 (Kabupaten Karawang)
untuk var 571 (TPAK) dan var 570 (TPT). Angka acuan diambil langsung dari
respons itu.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.official_statistics_service import (
    _DATASET_DEFINITIONS,
    OfficialStatisticsService,
)

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "bps"

# Nilai acuan seri 2013-2025.
_TPAK_2025 = 65.13
_TPT_2025 = 7.99
_TPT_2024 = 8.04
_TPT_TERTINGGI = (2021, 11.83)
_TPAK_TERENDAH = (2015, 58.9)
_TAHUN_TANPA_RILIS = 2016


def _load_fixture(name: str) -> dict:
    return json.loads((_FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _definition():
    return next(item for item in _DATASET_DEFINITIONS if item.key == "tpt_tpak")


@pytest.fixture
def service() -> OfficialStatisticsService:
    # Normalizer murni fungsi transformasi; client BPS tidak pernah dipanggil.
    return OfficialStatisticsService.__new__(OfficialStatisticsService)


def _normalize(service: OfficialStatisticsService, year: int) -> dict:
    return service._normalize_ketenagakerjaan(
        _definition(),
        {
            "tpak": _load_fixture("var571_seri.json"),
            "tpt": _load_fixture("var570_seri.json"),
        },
        year,
    )


def test_composite_key_assembly_yields_official_values(service):
    dataset = _normalize(service, 2026)
    latest = next(point for point in dataset["series"] if point["year"] == 2025)
    assert latest["tpak"] == pytest.approx(_TPAK_2025, abs=0.01)
    assert latest["tpt"] == pytest.approx(_TPT_2025, abs=0.01)
    assert latest["tpt_display"] == "7,99"


def test_series_is_sorted_and_skips_year_without_release(service):
    dataset = _normalize(service, 2026)
    years = [point["year"] for point in dataset["series"]]
    assert years == sorted(years)
    assert _TAHUN_TANPA_RILIS not in years
    assert years[0] == 2013 and years[-1] == 2025


def test_series_is_capped_at_selected_year(service):
    dataset = _normalize(service, 2024)
    assert max(point["year"] for point in dataset["series"]) == 2024
    assert dataset["latest_year"] == 2024
    assert dataset["is_latest_fallback"] is False


def test_unreleased_selected_year_falls_back_and_is_flagged(service):
    dataset = _normalize(service, 2026)
    assert dataset["available"] is True
    assert dataset["latest_year"] == 2025
    # Tahun terpilih belum dirilis BPS, jadi kartu wajib menandainya.
    assert dataset["is_latest_fallback"] is True


def test_change_compares_against_previous_filled_year(service):
    tpt = _normalize(service, 2026)["indicators"]["tpt"]
    assert tpt["total"] == pytest.approx(_TPT_2025, abs=0.01)
    assert tpt["change"]["previous_year"] == 2024
    assert tpt["change"]["previous_value"] == pytest.approx(_TPT_2024, abs=0.01)
    assert tpt["change"]["delta_value"] == pytest.approx(_TPT_2025 - _TPT_2024, abs=0.01)


def test_change_skips_gap_year_when_picking_previous_point(service):
    """2016 tidak dirilis, jadi pembanding 2017 harus 2015, bukan nilai kosong."""
    dataset = _normalize(service, 2017)
    tpak = dataset["indicators"]["tpak"]
    assert tpak["latest_year"] == 2017
    assert tpak["change"]["previous_year"] == 2015


def test_extremes_come_from_the_visible_series(service):
    indicators = _normalize(service, 2026)["indicators"]
    assert indicators["tpt"]["highest"]["year"] == _TPT_TERTINGGI[0]
    assert indicators["tpt"]["highest"]["value"] == pytest.approx(_TPT_TERTINGGI[1], abs=0.01)
    assert indicators["tpak"]["lowest"]["year"] == _TPAK_TERENDAH[0]
    assert indicators["tpak"]["lowest"]["value"] == pytest.approx(_TPAK_TERENDAH[1], abs=0.01)


def test_year_before_series_start_is_unavailable_without_raising(service):
    dataset = _normalize(service, 2010)
    assert dataset["available"] is False
    assert dataset["message"]


def test_empty_payload_is_unavailable(service):
    empty = _load_fixture("var570_2026_kosong.json")
    # Tahun tanpa data mengembalikan `datacontent` sebagai list kosong, bukan objek.
    assert empty["datacontent"] == []

    dataset = service._normalize_ketenagakerjaan(
        _definition(), {"tpak": empty, "tpt": empty}, 2026
    )
    assert dataset["available"] is False


def test_failed_source_does_not_kill_the_other_indicator(service):
    dataset = service._normalize_ketenagakerjaan(
        _definition(),
        {
            "tpak": {"status": "ERROR", "message": "gagal"},
            "tpt": _load_fixture("var570_seri.json"),
        },
        2026,
    )
    assert dataset["available"] is True
    assert dataset["indicators"]["tpt"]["total"] == pytest.approx(_TPT_2025, abs=0.01)
    assert dataset["indicators"]["tpak"]["total"] is None
    assert dataset["indicators"]["tpak"]["total_display"] == "—"


def test_ai_block_states_values_and_coverage_limit(service):
    dataset = _normalize(service, 2026)
    block = service._build_tpt_ai_block({"tpt_tpak": dataset}, 2026)

    assert "65,13 persen" in block
    assert "7,99 persen" in block
    assert "Jangan menyebut angka TPT atau TPAK 2026" in block
    # Seri lengkap ikut dikirim supaya model bisa menjawab pertanyaan tren.
    assert "2013: 60,54 / 9,80" in block


def test_ai_block_omits_coverage_note_when_year_is_released(service):
    dataset = _normalize(service, 2024)
    block = service._build_tpt_ai_block({"tpt_tpak": dataset}, 2024)
    assert "Catatan cakupan" not in block
