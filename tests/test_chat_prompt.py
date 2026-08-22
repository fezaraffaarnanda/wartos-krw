"""Perakitan prompt dan integritas sitasi AI Chat.

Fokusnya satu hal: pembaca harus bisa membedakan angka yang berasal dari
konteks resmi, angka dari berita, dan angka yang tidak berasal dari mana pun.
"""

from __future__ import annotations

from datetime import date

import pytest

import ai.chat as chat
from ai.kbli import KBLI_KEY_MAPPING
from services.official_statistics_service import OfficialStatisticsService

_TODAY = date(2026, 8, 22)


# ── Waktu ─────────────────────────────────────────────────────────────────

def test_prompt_states_todays_date():
    """Tanpa ini model tidak punya acuan untuk kata "bulan ini" / "terbaru"."""
    prompt = chat._build_user_prompt("apa kabar ekonomi?", "(kosong)", now=_TODAY)
    assert "22 Agustus 2026" in prompt


def test_prompt_carries_the_widening_warning():
    prompt = chat._build_user_prompt(
        "ekonomi bulan ini",
        "(kosong)",
        now=_TODAY,
        retrieval_meta={"widened_period": True},
    )
    assert "periode lain" in prompt


# ── Sitasi ────────────────────────────────────────────────────────────────

def test_statistic_markers_survive_sanitization():
    cite_map = {"S01": {"type": "berita"}, "BPS-TPT-2025": {"type": "statistik"}}
    answer = "TPT 7,99 persen [BPS-TPT-2025] sejalan dengan rekrutmen pabrik [S01]."
    assert chat.sanitize_answer_citation_tokens(answer, cite_map) == answer


def test_invented_markers_are_stripped():
    cite_map = {"S01": {"type": "berita"}}
    answer = "Angka 12,3 persen [BPS-NGAWUR-2030] dan klaim lain [S09]."
    cleaned = chat.sanitize_answer_citation_tokens(answer, cite_map)
    assert "BPS-NGAWUR-2030" not in cleaned
    assert "S09" not in cleaned


def test_citation_ids_include_statistic_blocks():
    ids = chat.extract_citation_ids_from_answer("a [S02] b [BPS-KEMISKINAN-2025] c [S02]")
    assert ids == ["S02", "BPS-KEMISKINAN-2025"]


def test_answer_without_markers_gets_no_citations():
    """Dulu dua dokumen teratas dikembalikan seolah-olah dikutip -- sumber
    palsu yang dibuat oleh kode kita sendiri, bukan oleh model."""
    cite_map = {"S01": {"title": "a"}, "S02": {"title": "b"}}
    assert chat.finalize_citations("Jawaban tanpa marker sama sekali.", cite_map) == []


def test_history_markers_are_stripped_for_both_kinds():
    text = "Klaim [S01] dan angka [BPS-PDRB-2026-Q1] lama."
    assert "S01" not in chat._HISTORY_CITATION_RE.sub("", text)
    assert "BPS-PDRB" not in chat._HISTORY_CITATION_RE.sub("", text)


# ── Taksonomi KBLI ────────────────────────────────────────────────────────

def test_system_prompt_ships_the_real_kbli_catalog():
    """Prompt lama mewajibkan sebut KBLI tapi tidak pernah mengirim daftarnya,
    dan contohnya sendiri memakai kode karangan ("C5")."""
    # "C5" sekarang hanya boleh muncul sebagai contoh yang DILARANG.
    assert "khususnya subkategori C5" not in chat._SYSTEM_PROMPT
    for code, label in KBLI_KEY_MAPPING.items():
        assert f"- {code} — {label}" in chat._SYSTEM_PROMPT


def test_system_prompt_forbids_invented_subcategories():
    assert "Dilarang menyebut subkategori bernomor" in chat._SYSTEM_PROMPT


def test_system_prompt_requires_markers_for_official_numbers():
    assert "Setiap angka statistik resmi WAJIB diakhiri penanda" in chat._SYSTEM_PROMPT


# ── Deteksi topik statistik ───────────────────────────────────────────────

@pytest.mark.parametrize(
    "query, expected",
    [
        ("berapa inflasi terbaru", {"pdrb", "kemiskinan", "pengangguran"}),
        ("bagaimana upah buruh di karawang", {"pengangguran"}),
        ("gini ratio berapa", {"kemiskinan"}),
        ("realisasi investasi triwulan I", {"pdrb"}),
        ("resep rendang", set()),
    ],
)
def test_topic_detection_covers_common_wording(query, expected):
    assert OfficialStatisticsService.detect_chat_topics(query) == expected


def test_word_boundary_prevents_false_topic_matches():
    """Pencocokan substring lama membuat "importir" menyulut topik PDRB."""
    assert "pdrb" not in OfficialStatisticsService.detect_chat_topics("kabar importir lokal")
