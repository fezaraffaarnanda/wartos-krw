"""Tes normalizer seri kemiskinan terhadap isi sheet sumber apa adanya.

Fixture `tests/fixtures/sheets/kemiskinan.json` adalah hasil `GoogleSheetsClient`
atas sheet "Kemiskinan" (matriks lebar: kolom = tahun menurun, baris = metrik).
Angka acuan diambil langsung dari sheet itu.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from services.official_statistics_service import (
    _DATASET_DEFINITIONS,
    OfficialStatisticsService,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "sheets" / "kemiskinan.json"

# Nilai acuan.
_P0_2025 = 7.08
_P0_2024 = 7.86
_JIWA_2025 = 169.78
_GK_2025 = 617_901.0
_GINI_2025 = 0.360
_P0_TERTINGGI = (2006, 16.51)
_TAHUN_AWAL = 2004
_GINI_TAHUN_AWAL = 2021


def _payload() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _definition():
    return next(item for item in _DATASET_DEFINITIONS if item.key == "kemiskinan")


@pytest.fixture
def service() -> OfficialStatisticsService:
    # Normalizer murni fungsi transformasi; client Sheets tidak pernah dipanggil.
    return OfficialStatisticsService.__new__(OfficialStatisticsService)


def _normalize(service: OfficialStatisticsService, year: int, payload: dict | None = None) -> dict:
    return service._normalize_kemiskinan_series(
        _definition(), {"sheet": payload or _payload()}, year
    )


def test_wide_sheet_is_transposed_into_ascending_series(service):
    dataset = _normalize(service, 2026)
    years = [point["year"] for point in dataset["series"]]
    assert years == sorted(years)
    assert years[0] == _TAHUN_AWAL and years[-1] == 2025


def test_latest_point_matches_sheet_values(service):
    latest = _normalize(service, 2026)["series"][-1]
    assert latest["poverty_rate"] == pytest.approx(_P0_2025, abs=0.01)
    assert latest["poor_population"] == pytest.approx(_JIWA_2025, abs=0.01)
    assert latest["poverty_line"] == pytest.approx(_GK_2025, abs=0.5)
    assert latest["gini_ratio"] == pytest.approx(_GINI_2025, abs=0.001)


def test_thousand_separator_in_poverty_line_is_not_read_as_decimal(service):
    """"617,901" di sheet berarti 617.901 rupiah, bukan 617,901."""
    poverty_line = _normalize(service, 2026)["metrics"]["poverty_line"]
    assert poverty_line["value"] == pytest.approx(_GK_2025, abs=0.5)
    assert poverty_line["value_display"] == "617.901"


def test_two_rows_under_one_label_are_split_by_unit(service):
    """Baris "P0/Persen" dan baris tanpa label "/Ribuan Jiwa" tidak boleh tertukar."""
    metrics = _normalize(service, 2026)["metrics"]
    assert metrics["poverty_rate"]["value"] == pytest.approx(_P0_2025, abs=0.01)
    assert metrics["poor_population"]["value"] == pytest.approx(_JIWA_2025, abs=0.01)


def test_series_is_capped_at_selected_year(service):
    dataset = _normalize(service, 2020)
    assert max(point["year"] for point in dataset["series"]) == 2020
    assert dataset["latest_year"] == 2020
    assert dataset["is_latest_fallback"] is False


def test_unreleased_selected_year_falls_back_and_is_flagged(service):
    dataset = _normalize(service, 2026)
    assert dataset["latest_year"] == 2025
    assert dataset["is_latest_fallback"] is True


def test_metric_without_early_data_stays_empty_instead_of_guessing(service):
    """Gini Ratio baru ada sejak 2021; tahun sebelumnya harus kosong, bukan 0."""
    dataset = _normalize(service, 2019)
    assert dataset["metrics"]["gini_ratio"]["value"] is None
    assert dataset["metrics"]["gini_ratio"]["latest_year"] is None
    assert all(point["gini_ratio"] is None for point in dataset["series"])

    dataset_2021 = _normalize(service, 2021)
    assert dataset_2021["metrics"]["gini_ratio"]["latest_year"] == _GINI_TAHUN_AWAL


def test_change_uses_metric_own_unit_and_format(service):
    metrics = _normalize(service, 2026)["metrics"]
    assert metrics["poverty_rate"]["change"]["previous_year"] == 2024
    assert metrics["poverty_rate"]["change"]["delta_value"] == pytest.approx(
        _P0_2025 - _P0_2024, abs=0.01
    )
    assert metrics["poverty_rate"]["change"]["delta_display"] == "-0,78 poin"
    # Selisih garis kemiskinan adalah rupiah utuh, bukan "poin" dua desimal.
    assert metrics["poverty_line"]["change"]["delta_display"] == "+20.556 rupiah"
    assert metrics["poor_population"]["change"]["delta_display"].endswith(" ribu jiwa")


def test_extremes_come_from_the_visible_series(service):
    poverty_rate = _normalize(service, 2026)["metrics"]["poverty_rate"]
    assert poverty_rate["highest"]["year"] == _P0_TERTINGGI[0]
    assert poverty_rate["highest"]["value"] == pytest.approx(_P0_TERTINGGI[1], abs=0.01)
    assert poverty_rate["lowest"]["year"] == 2025


def test_year_before_series_start_is_unavailable_without_raising(service):
    dataset = _normalize(service, 2000)
    assert dataset["available"] is False
    assert dataset["message"]


def test_failed_fetch_is_unavailable(service):
    dataset = service._normalize_kemiskinan_series(
        _definition(), {"sheet": {"status": "ERROR", "message": "gagal"}}, 2026
    )
    assert dataset["available"] is False
    assert dataset["message"] == "gagal"


def test_unknown_row_label_is_ignored(service):
    payload = _payload()
    payload["rows"].append(["Catatan", "", "abaikan saya"])
    dataset = _normalize(service, 2026, payload)
    assert dataset["available"] is True
    assert set(dataset["metrics"]) == {
        "poverty_rate",
        "poor_population",
        "depth_index",
        "severity_index",
        "poverty_line",
        "gini_ratio",
    }


def test_reordered_year_columns_are_read_by_header_not_position(service):
    """Urutan kolom diambil dari header, jadi sheet yang dibalik tetap benar."""
    payload = _payload()
    reversed_rows = [row[:2] + list(reversed(row[2:])) for row in payload["rows"]]
    payload["rows"] = reversed_rows

    dataset = _normalize(service, 2026, payload)
    latest = dataset["series"][-1]
    assert latest["year"] == 2025
    assert latest["poverty_rate"] == pytest.approx(_P0_2025, abs=0.01)


def test_ai_block_states_values_and_coverage_limit(service):
    dataset = _normalize(service, 2026)
    block = service._build_kemiskinan_ai_block({"kemiskinan": dataset}, 2026)

    assert "7,08 Persen" in block
    assert "617.901 Rp/kapita/bulan" in block
    assert "Jangan menyebut angka kemiskinan 2026" in block
    # Seri lengkap ikut dikirim supaya model bisa menjawab pertanyaan tren.
    assert "2004: 13,28 / 252,10" in block


def test_ai_block_omits_coverage_note_when_year_is_present(service):
    dataset = _normalize(service, 2024)
    block = service._build_kemiskinan_ai_block({"kemiskinan": dataset}, 2024)
    assert "Catatan cakupan" not in block


def test_normalizer_does_not_mutate_the_source_payload(service):
    payload = _payload()
    snapshot = deepcopy(payload)
    _normalize(service, 2026, payload)
    assert payload == snapshot
