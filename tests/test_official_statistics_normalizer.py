"""Tes normalizer PDRB triwulanan terhadap payload asli Web API BPS.

Fixture di `tests/fixtures/bps/` adalah respons apa adanya dari
`webapi.bps.go.id/v1/api/list/model/data` domain 3215 (Kabupaten Karawang),
th/126 = 2026. Angka acuan di bawah diambil langsung dari respons itu.
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

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "bps"

# Nilai acuan Triwulan I 2026.
_TOTAL_ADHB = 86_126.45
_TOTAL_ADHK = 51_763.61
_INDUSTRI_PENGOLAHAN_ADHB = 58_373.02
_KONSUMSI_RUMAH_TANGGA_SHARE = 38.67


def _load_fixture(name: str) -> dict:
    return json.loads((_FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _definition(key: str):
    return next(item for item in _DATASET_DEFINITIONS if item.key == key)


@pytest.fixture
def service() -> OfficialStatisticsService:
    # Normalizer murni fungsi transformasi; client BPS tidak pernah dipanggil.
    return OfficialStatisticsService.__new__(OfficialStatisticsService)


@pytest.fixture
def lapangan_usaha(service) -> dict:
    return service._normalize_pdrb_triwulanan(
        _definition("pdrb_lapangan_usaha"),
        {
            "adhb": _load_fixture("var610_2026.json"),
            "adhk": _load_fixture("var611_2026.json"),
            "distribusi": _load_fixture("var612_2026.json"),
        },
        2026,
    )


@pytest.fixture
def pengeluaran(service) -> dict:
    return service._normalize_pdrb_triwulanan(
        _definition("pdrb_pengeluaran"),
        {
            "adhb": _load_fixture("var617_2026.json"),
            "adhk": _load_fixture("var618_2026.json"),
            "distribusi": _load_fixture("var619_2026.json"),
        },
        2026,
    )


def test_composite_key_assembly_yields_official_values(lapangan_usaha):
    total = lapangan_usaha["by_period"]["q1"]["total"]
    assert total["adhb"] == pytest.approx(_TOTAL_ADHB, abs=0.01)
    assert total["adhk"] == pytest.approx(_TOTAL_ADHK, abs=0.01)
    assert total["adhb_display"] == "86.126,45"

    industri = next(
        row for row in lapangan_usaha["by_period"]["q1"]["rows"]
        if row["label"] == "Industri Pengolahan"
    )
    assert industri["adhb"] == pytest.approx(_INDUSTRI_PENGOLAHAN_ADHB, abs=0.01)
    assert industri["code"] == "C"


def test_lapangan_usaha_rows_sum_to_total(lapangan_usaha):
    rows = lapangan_usaha["by_period"]["q1"]["rows"]
    assert len(rows) == 17
    assert sum(row["adhb"] for row in rows) == pytest.approx(_TOTAL_ADHB, abs=0.01)
    assert sum(row["adhk"] for row in rows) == pytest.approx(_TOTAL_ADHK, abs=0.01)
    assert sum(row["share"] for row in rows) == pytest.approx(100.0, abs=0.01)


def test_rows_sorted_by_adhb_descending(lapangan_usaha):
    values = [row["adhb"] for row in lapangan_usaha["by_period"]["q1"]["rows"]]
    assert values == sorted(values, reverse=True)


def test_var_617_unlabeled_period_maps_to_quarter_one(pengeluaran):
    """Var 617 melaporkan turtahun 0/Tahun, bukan 31/Triwulan I."""
    raw = _load_fixture("var617_2026.json")
    assert [item["val"] for item in raw["turtahun"]] == [0]

    total = pengeluaran["by_period"]["q1"]["total"]
    assert total["adhb"] == pytest.approx(_TOTAL_ADHB, abs=0.05)
    assert total["adhk"] == pytest.approx(_TOTAL_ADHK, abs=0.01)


def test_pengeluaran_uses_aggregate_row_and_drops_it_from_rows(pengeluaran):
    rows = pengeluaran["by_period"]["q1"]["rows"]
    assert len(rows) == 6
    assert all(row["label"] != "Produk Domestik Regional Bruto" for row in rows)

    konsumsi = next(row for row in rows if row["label"] == "Pengeluaran Konsumsi Rumah Tangga")
    assert konsumsi["share"] == pytest.approx(_KONSUMSI_RUMAH_TANGGA_SHARE, abs=0.01)


def test_only_filled_periods_are_marked_available(lapangan_usaha):
    availability = {period["period_key"]: period["available"] for period in lapangan_usaha["periods"]}
    assert availability == {"q1": True, "q2": False, "q3": False, "q4": False, "annual": False}
    assert lapangan_usaha["default_period_key"] == "q1"


def test_implicit_index_is_adhb_over_adhk(lapangan_usaha):
    total = lapangan_usaha["by_period"]["q1"]["total"]
    assert total["implicit_index"] == pytest.approx(_TOTAL_ADHB / _TOTAL_ADHK * 100, abs=0.01)


def test_share_falls_back_to_computed_ratio_when_distribusi_missing(service):
    dataset = service._normalize_pdrb_triwulanan(
        _definition("pdrb_lapangan_usaha"),
        {
            "adhb": _load_fixture("var610_2026.json"),
            "adhk": _load_fixture("var611_2026.json"),
            "distribusi": {"status": "ERROR", "message": "gagal"},
        },
        2026,
    )
    industri = next(
        row for row in dataset["by_period"]["q1"]["rows"]
        if row["label"] == "Industri Pengolahan"
    )
    assert industri["share"] == pytest.approx(_INDUSTRI_PENGOLAHAN_ADHB / _TOTAL_ADHB * 100, abs=0.01)


def test_empty_year_is_unavailable_without_raising(service):
    empty = _load_fixture("var610_2025_kosong.json")
    # Tahun tanpa data mengembalikan `datacontent` sebagai list kosong, bukan objek.
    assert empty["datacontent"] == []

    dataset = service._normalize_pdrb_triwulanan(
        _definition("pdrb_lapangan_usaha"),
        {"adhb": empty, "adhk": deepcopy(empty), "distribusi": deepcopy(empty)},
        2025,
    )
    assert dataset["available"] is False
    assert dataset["by_period"] == {}
    assert dataset["message"]


def test_ambiguous_unlabeled_period_is_dropped_not_guessed(service):
    """Kalau saudara-saudaranya punya dua triwulan, periode tak berlabel tidak ditebak."""
    adhb = _load_fixture("var617_2026.json")
    adhk = _load_fixture("var618_2026.json")

    # Duplikasi Triwulan I var 618 jadi Triwulan II supaya ada dua kandidat.
    adhk["turtahun"].append({"val": 32, "label": "Triwulan II"})
    adhk["datacontent"].update(
        {key[:-2] + "32": value for key, value in list(adhk["datacontent"].items())}
    )

    dataset = service._normalize_pdrb_triwulanan(
        _definition("pdrb_pengeluaran"),
        {"adhb": adhb, "adhk": adhk, "distribusi": _load_fixture("var619_2026.json")},
        2026,
    )

    assert set(dataset["by_period"]) == {"q1", "q2"}
    # Nilai ADHB dari var 617 dibuang, jadi share jatuh ke fallback dan ADHB kosong.
    assert all(row["adhb"] is None for row in dataset["by_period"]["q1"]["rows"])
