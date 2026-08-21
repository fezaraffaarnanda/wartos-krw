"""Jalur Audit Relevance harus dibatasi ke sumber berita wilayah fokus.

Tabel `berita` masih menyimpan baris warisan wilayah lama (era Kabupaten
Tegal) yang sengaja tidak dihapus. Sebelum perubahan ini tidak satu pun query
di jalur relevance menyaringnya, sehingga antrean "Gagal Diklasifikasi",
metrik precision/recall, few-shot export, dan feeder backfill semuanya ikut
memproses berita wilayah lain.

Yang diuji di sini adalah *predikat yang dikirim ke Supabase*, bukan hasilnya:
stub di bawah merekam setiap pemanggilan method pada query builder.
"""

from __future__ import annotations

from typing import Any

import pytest

from config.region import FOCUS_AREA_SOURCES
from repositories.berita import BeritaRepository
from repositories.relevance_audit import RelevanceAuditRepository

_EXPECTED_SOURCES = list(FOCUS_AREA_SOURCES)


class _RecordingQuery:
    """Query builder palsu: semua method mengembalikan diri sendiri sambil
    mencatat (nama, *args). `not_` adalah properti di client Supabase, jadi
    dipetakan ke objek yang sama supaya `.not_.is_(...)` ikut terekam."""

    def __init__(self, calls: list[tuple], rows: list[dict[str, Any]], count: int):
        self._calls = calls
        self.data = rows
        self.count = count

    @property
    def not_(self) -> "_RecordingQuery":
        return self

    def execute(self) -> "_RecordingQuery":
        return self

    def __getattr__(self, name: str):
        def _record(*args, **kwargs):
            self._calls.append((name, *args))
            return self

        return _record


class _RecordingSupabase:
    def __init__(self, rows: list[dict[str, Any]] | None = None, count: int = 0):
        self.calls: list[tuple] = []
        self._rows = rows or []
        self._count = count

    def table(self, name: str) -> _RecordingQuery:
        self.calls.append(("table", name))
        return _RecordingQuery(self.calls, self._rows, self._count)


def _source_filters(supabase: _RecordingSupabase) -> list[tuple]:
    return [call for call in supabase.calls if call[0] == "in_" and call[1] == "source"]


def _assert_scoped(supabase: _RecordingSupabase) -> None:
    filters = _source_filters(supabase)
    assert filters, f"tidak ada filter sumber; calls={supabase.calls}"
    assert all(call[2] == _EXPECTED_SOURCES for call in filters)


@pytest.mark.parametrize(
    "mode",
    ["uncertainty", "failed", "labeled", "all", "disagreement", "audit"],
)
def test_review_queue_is_scoped_in_every_mode(mode):
    supabase = _RecordingSupabase()
    repo = BeritaRepository(supabase)
    repo.list_relevance_review_rows(mode=mode, audit_berita_ids=[1, 2])
    _assert_scoped(supabase)


def test_disagreement_mode_is_scoped_even_though_it_filters_in_python():
    """Cabang ini menyelesaikan filternya di Python setelah execute(), jadi
    batasan sumber wajib ikut lewat _apply_common, bukan per-cabang."""
    rows = [
        {"id": 1, "human_label": True, "is_relevant": False},
        {"id": 2, "human_label": False, "is_relevant": False},
    ]
    supabase = _RecordingSupabase(rows=rows)
    repo = BeritaRepository(supabase)
    result = repo.list_relevance_review_rows(mode="disagreement")

    _assert_scoped(supabase)
    assert [row["id"] for row in result["data"]] == [1]


def test_explicit_source_filter_does_not_widen_the_region_scope():
    supabase = _RecordingSupabase()
    repo = BeritaRepository(supabase)
    repo.list_relevance_review_rows(mode="failed", source="Radar Karawang")

    _assert_scoped(supabase)
    assert ("eq", "source", "Radar Karawang") in supabase.calls


def test_failed_queue_still_filters_on_unchecked_rows():
    """Batasan wilayah tidak boleh menggantikan predikat mode-nya."""
    supabase = _RecordingSupabase()
    repo = BeritaRepository(supabase)
    repo.list_relevance_review_rows(mode="failed")

    _assert_scoped(supabase)
    assert ("is_", "relevance_checked_at", "null") in supabase.calls


@pytest.mark.parametrize(
    "invoke",
    [
        pytest.param(lambda repo: repo.count_unchecked_relevance(), id="count_unchecked"),
        pytest.param(lambda repo: repo.list_unchecked_relevance_rows(), id="backfill_feeder"),
        pytest.param(lambda repo: repo.list_labeled_rows(), id="few_shot_export"),
        pytest.param(lambda repo: repo.relevance_confusion_rows(), id="confusion_matrix"),
        pytest.param(lambda repo: repo.count_scored_by_band(), id="band_population"),
    ],
)
def test_supporting_relevance_queries_are_scoped(invoke):
    supabase = _RecordingSupabase()
    repo = BeritaRepository(supabase)
    invoke(repo)
    _assert_scoped(supabase)


def test_band_population_counts_instead_of_scanning_rows():
    """Versi lama menarik seluruh baris berskor 1000-per-halaman hanya untuk
    menghitungnya. Sekarang lima count query kecil, tanpa transfer baris."""
    supabase = _RecordingSupabase(count=12)
    repo = BeritaRepository(supabase)
    counts = repo.count_scored_by_band()

    assert set(counts) == {"b00_19", "b20_39", "b40_59", "b60_79", "b80_100"}
    assert all(value == 12 for value in counts.values())
    assert [c for c in supabase.calls if c[0] == "range"] == []
    assert len([c for c in supabase.calls if c[0] == "select"]) == 5
    _assert_scoped(supabase)


def test_label_context_query_does_not_pull_article_content():
    """Menyimpan label tidak boleh ikut memindahkan isi artikel penuh."""
    supabase = _RecordingSupabase(rows={"id": 1, "human_label": None})
    repo = BeritaRepository(supabase)
    repo.get_relevance_label_context(1)

    selects = [call for call in supabase.calls if call[0] == "select"]
    assert selects, supabase.calls
    assert "content" not in selects[0][1]
    assert ("eq", "id", 1) in supabase.calls


class _RecordingRpc:
    def __init__(self):
        self.params: dict[str, Any] | None = None
        self.data = 7

    def rpc(self, name: str, params: dict[str, Any]) -> "_RecordingRpc":
        self.name = name
        self.params = params
        return self

    def execute(self) -> "_RecordingRpc":
        return self


def test_audit_sample_rpc_receives_focus_area_sources():
    """Sampel acak hanya "tak bias" kalau populasinya wilayah fokus saja."""
    client = _RecordingRpc()
    repo = RelevanceAuditRepository(client)
    batch_id = repo.draw_sample(batch_key="audit-1", per_band=20, created_by="admin")

    assert batch_id == 7
    assert client.params["p_sources"] == _EXPECTED_SOURCES
