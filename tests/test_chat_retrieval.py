"""Bahan yang boleh masuk jawaban AI Chat.

Audit atas percakapan nyata menemukan jawaban yang menganalisis wilayah lain
(Bumijawa, Guci) dan mengutip berita kriminal sebagai bukti ekonomi: retrieval
menarik dari seluruh tabel berita tanpa filter wilayah maupun relevansi. Tes di
sini menjaga batas itu tanpa memanggil LLM sama sekali.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

import ai.chat as chat
from config.region import FOCUS_AREA_SOURCES

_SOURCES = list(FOCUS_AREA_SOURCES)
_TODAY = date(2026, 8, 22)


class _FakeSearch:
    """Perekam pemanggilan semantic_search; mengembalikan hasil per giliran."""

    def __init__(self, results: list[list[dict[str, Any]]]):
        self._results = results
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        idx = min(len(self.calls) - 1, len(self._results) - 1)
        return self._results[idx]


def _doc(doc_id: int, *, similarity: float = 0.6, day: str = "2026-08-01") -> dict[str, Any]:
    return {
        "id": doc_id,
        "title": f"Berita {doc_id}",
        "content": "isi",
        "source": "Radar Karawang",
        "url": f"https://example.test/{doc_id}",
        "date": day,
        "date_parsed": day,
        "similarity": similarity,
    }


@pytest.fixture
def fake_search(monkeypatch):
    def _install(results):
        stub = _FakeSearch(results)
        monkeypatch.setattr(chat, "semantic_search", stub)
        monkeypatch.setattr(chat, "_keyword_fallback_search", lambda *a, **k: [])
        return stub

    return _install


# ── Batas wilayah ─────────────────────────────────────────────────────────

def test_retrieval_is_always_scoped_to_focus_area_and_active_rows(fake_search):
    stub = fake_search([[_doc(i) for i in range(1, 6)]])
    chat.retrieve_context("pertumbuhan restoran", object(), now=_TODAY)

    assert stub.calls, "semantic_search tidak dipanggil"
    for call in stub.calls:
        assert call["sources"] == _SOURCES
        assert call["exclude_archived"] is True


def test_widening_never_drops_the_region_filter(fake_search):
    """Pelebaran hanya melonggarkan relevansi dan tanggal, tidak wilayah."""
    stub = fake_search([[], [], [_doc(1), _doc(2), _doc(3), _doc(4)]])
    chat.retrieve_context("kondisi ekonomi bulan ini", object(), now=_TODAY)

    assert len(stub.calls) >= 2
    assert all(call["sources"] == _SOURCES for call in stub.calls)


# ── Relevansi bertingkat ──────────────────────────────────────────────────

def test_first_pass_requires_the_relevance_gate(fake_search):
    stub = fake_search([[_doc(i) for i in range(1, 6)]])
    chat.retrieve_context("dampak PHK", object(), now=_TODAY)

    assert stub.calls[0]["only_relevant"] is True
    assert len(stub.calls) == 1, "tidak perlu melebar saat hasil sudah cukup"


def test_widens_past_the_relevance_gate_only_when_results_are_thin(fake_search):
    stub = fake_search([[_doc(1)], [_doc(i) for i in range(1, 7)]])
    docs, meta = chat.retrieve_context("isu niche", object(), now=_TODAY)

    assert [call["only_relevant"] for call in stub.calls] == [True, False]
    assert meta["widened_relevance"] is True
    assert len(docs) == 6


def test_widening_is_reported_so_the_prompt_can_say_so(fake_search):
    fake_search([[_doc(1)], [_doc(i) for i in range(1, 7)]])
    _docs, meta = chat.retrieve_context("isu niche", object(), now=_TODAY)
    note = chat._build_retrieval_note(meta)
    assert "belum tentu bermuatan ekonomi" in note


# ── Periode ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "query, expected",
    [
        ("bagaimana ekonomi bulan ini?", ("2026-08-01", "2026-08-22")),
        ("kondisi bulan lalu", ("2026-07-01", "2026-07-31")),
        ("fenomena triwulan III 2026", ("2026-07-01", "2026-09-30")),
        ("pdrb triwulan IV 2025", ("2025-10-01", "2025-12-31")),
        ("data 2024", ("2024-01-01", "2024-12-31")),
        ("tahun lalu bagaimana", ("2025-01-01", "2025-12-31")),
        ("sektor apa yang dominan", (None, None)),
    ],
)
def test_detect_requested_period(query, expected):
    assert chat.detect_requested_period(query, now=_TODAY) == expected


def test_period_filter_is_sent_then_dropped_when_it_starves_retrieval(fake_search):
    stub = fake_search([[_doc(1)], [_doc(i) for i in range(1, 7)]])
    _docs, meta = chat.retrieve_context("ekonomi bulan ini", object(), now=_TODAY)

    assert stub.calls[0]["date_from"] == "2026-08-01"
    assert stub.calls[1]["date_from"] is None
    assert meta["widened_period"] is True


# ── Peringkat kebaruan ────────────────────────────────────────────────────

def test_recent_doc_wins_on_equal_similarity():
    old = _doc(1, similarity=0.7, day="2025-08-01")
    new = _doc(2, similarity=0.7, day="2026-08-01")
    ranked = chat.rank_docs_by_similarity_and_recency([old, new], now=_TODAY)
    assert [d["id"] for d in ranked] == [2, 1]


def test_much_more_similar_old_doc_still_wins():
    """Kebaruan itu bobot, bukan filter -- berita lama yang jauh lebih relevan
    tetap boleh menang."""
    old = _doc(1, similarity=0.95, day="2025-11-01")
    new = _doc(2, similarity=0.30, day="2026-08-20")
    ranked = chat.rank_docs_by_similarity_and_recency([old, new], now=_TODAY)
    assert ranked[0]["id"] == 1


def test_doc_without_date_sinks_but_is_not_dropped():
    dated = _doc(1, similarity=0.5, day="2026-08-01")
    undated = _doc(2, similarity=0.5)
    undated["date_parsed"] = None
    ranked = chat.rank_docs_by_similarity_and_recency([undated, dated], now=_TODAY)
    assert [d["id"] for d in ranked] == [1, 2]


# ── Penandaan berita lama di konteks ──────────────────────────────────────

def test_stale_news_is_flagged_in_the_context_block():
    """Jawaban lama menyajikan berita September 2025 sebagai kondisi terkini."""
    text, _cites = chat._format_context_docs([_doc(1, day="2025-09-12")], now=_TODAY)
    assert "SUDAH LAMA" in text

    fresh, _ = chat._format_context_docs([_doc(2, day="2026-08-01")], now=_TODAY)
    assert "SUDAH LAMA" not in fresh


# ── Pertanyaan susulan ────────────────────────────────────────────────────

def test_anaphoric_followup_carries_the_previous_question():
    history = [
        {"role": "user", "content": "bagaimana kondisi kemiskinan Karawang?"},
        {"role": "assistant", "content": "jawaban panjang"},
    ]
    merged = chat._build_search_query("kenapa begitu?", history)
    assert "kemiskinan" in merged
    assert "kenapa begitu?" in merged


def test_self_contained_question_is_not_polluted_by_history():
    history = [{"role": "user", "content": "bagaimana kondisi kemiskinan Karawang?"}]
    query = "Berapa nilai PDRB sektor industri pengolahan triwulan I 2026?"
    assert chat._build_search_query(query, history) == query
