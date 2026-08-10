import pytest

from config.region import FOCUS_AREA_SOURCES, OFFICIAL_PERSON_TAGS
from utils.tags import DROP_REASONS, clean_tags, inspect_tags, split_tags


@pytest.mark.parametrize("raw,expected", [
    ("Radar Karawang | Inflasi", "Inflasi"),
    ("radarkarawang, inflasi", "inflasi"),
    ("Radar-Karawang | Inflasi", "Inflasi"),
    ("radarkarawang.com | Inflasi", "Inflasi"),
    ("@radarkarawang | Inflasi", "Inflasi"),
    ("Aep Syaepuloh | UMKM", "UMKM"),
    ("aep saefullah,umkm", "umkm"),
    ("Bupati Aep Syaepuloh | Ekspor", "Ekspor"),
    ("H. Aep Syaepuloh | Ekspor", "Ekspor"),
])
def test_removes_source_identity_and_officials(raw, expected):
    assert clean_tags(raw) == expected


@pytest.mark.parametrize("keep", [
    "Pupuk Indonesia",
    "Dongsung Chemical",
    "PT Pupuk Kujang",
    "Kawasan Industri",
    "Aeon Mall",  # mirip 'aep' — heuristik fuzzy akan salah buang
    "Bupati",  # jabatan telanjang = topik sah
    "Kepala Dinas Perdagangan",  # institusi, bukan orang
    "Upah Minimum",
])
def test_keeps_legitimate_entities(keep):
    """Regresi utama: aturan nama orang tidak boleh menyentuh nama badan usaha."""
    assert clean_tags(keep) == keep


def test_every_active_source_label_is_filtered():
    """Menambah scraper wajib disertai penyaringan identitasnya sebagai tag.

    Tanpa ini, sumber baru langsung mencemari tag chips, KPI top-tags, dan
    embedding — persis keluhan 'radarkarawang'.
    """
    for label in FOCUS_AREA_SOURCES:
        assert clean_tags(label) == "", label


def test_person_blocklist_entries_are_specific():
    """Cegah entri terlalu pendek ('Aep') yang akan ikut membuang 'Aeon'."""
    for name in OFFICIAL_PERSON_TAGS:
        tokens = name.split()
        assert len(tokens) >= 2, f"nama depan telanjang berbahaya: {name}"
        assert len(name) >= 8, name


def test_inspect_reports_reason_per_tag():
    assert dict(inspect_tags("Radar Karawang | Aep Syaepuloh | Karawang | Inflasi | inflasi")) == {
        "Radar Karawang": "sumber",
        "Aep Syaepuloh": "pejabat",
        "Karawang": "lokasi",
        "Inflasi": None,
        "inflasi": "duplikat",
    }


def test_clean_tags_is_idempotent():
    once = clean_tags("Radar Karawang | Bupati Aep Syaepuloh | Ekspor Otomotif")
    assert clean_tags(once) == once


def test_no_drop_reason_is_dead():
    """Setiap alasan yang dideklarasikan harus bisa dipicu — cegah aturan mati."""
    fixture = "1 | ab | 12 | berita | Radar Karawang | Aep Syaepuloh | Tegal | Ekspor | ekspor"
    assert {r for _t, r in inspect_tags(fixture) if r} == set(DROP_REASONS)


def test_split_tags_is_the_only_splitter():
    assert split_tags("a | b,c | #d") == ["a", "b", "c", "d"]
    assert split_tags(None) == []
    assert split_tags("") == []


def test_clean_tags_handles_empty_input():
    assert clean_tags(None) == ""
    assert clean_tags("") == ""


def test_comma_separated_degree_suffix_is_a_known_limitation():
    """split_tags membelah PADA koma, jadi 'Nama, S.H.' jadi dua tag terpisah
    ('Nama' dan 'S.H.'). 'Nama' tetap tersaring lewat aturan pejabat; 'S.H.'
    lolos sebagai tag noise 4-karakter. Diterima sebagai batas desain: tag
    berasal dari markup tag situs (satu <a> = satu tag), bukan kalimat bebas,
    jadi kombinasi "nama, gelar" dalam satu tag jarang terjadi di data nyata.
    Bila muncul, --report removed tetap memperlihatkannya untuk review manual.
    """
    assert clean_tags("Aep Syaepuloh, S.H.") == "S.H."
