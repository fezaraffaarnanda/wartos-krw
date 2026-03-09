"""
ai_insights.py — Modul AI Insight menggunakan DeepSeek LLM

Menganalisis berita dari database dan menghasilkan insight
untuk tiga kategori: PDRB, Kemiskinan, dan Pengangguran.
"""

import json
import os
import re

from openai import OpenAI

# ── Konstanta ──────────────────────────────────────────────────────────────────

_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
_DEEPSEEK_MODEL    = "deepseek-chat"

# Jumlah karakter konten per artikel yang dikirim ke LLM (hemat token)
_MAX_CONTENT_CHARS = 500
# Maks artikel per kategori yang dikirim ke LLM
_MAX_ARTICLES_PER_CAT = 30
# Maks sumber yang ditampilkan ke user per kategori
_MAX_SOURCES_SHOWN = 6

# Keyword per kategori — untuk pre-filter
_KEYWORDS: dict[str, list[str]] = {
    "pdrb": [
        "pdrb", "produk domestik regional bruto", "ekonomi", "pertumbuhan ekonomi",
        "lapangan usaha", "sektor", "industri", "pertanian", "perdagangan",
        "manufaktur", "jasa", "investasi", "ekspor", "impor", "inflasi",
        "deflasi", "harga", "komoditas", "pendapatan", "fiskal", "anggaran",
        "umkm", "koperasi", "pariwisata", "proyek", "infrastruktur",
    ],
    "kemiskinan": [
        "kemiskinan", "miskin", "bantuan sosial", "bansos", "blt",
        "program keluarga harapan", "pkh", "bpnt", "sembako", "raskin",
        "stunting", "gizi buruk", "penghasilan", "pendapatan rendah",
        "rumah layak huni", "bedah rumah", "dhuafa", "fakir", "yatim",
        "pengentasan", "sosial", "kesejahteraan", "bps", "data kemiskinan",
    ],
    "pengangguran": [
        "pengangguran", "angkatan kerja", "lapangan kerja", "pekerjaan",
        "tenaga kerja", "pekerja", "buruh", "tki", "tkw", "umk",
        "upah minimum", "phk", "pemutusan hubungan kerja", "rekrutmen",
        "lowongan", "job fair", "pelatihan kerja",
        "disnaker", "dinas tenaga kerja", "tpak", "tingkat pengangguran",
    ],
}

# ── Sistem prompt ──────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """Kamu adalah analis ekonomi daerah dari Badan Pusat Statistik (BPS) Kabupaten Tegal.
Tugasmu: analisis berita lokal dan hasilkan insight tajam, berbasis data, mudah dipahami stakeholder non-teknis.

Panduan:
1. Identifikasi tren utama (naik/turun/stabil) yang terlihat dari berita.
2. Sebutkan penyebab spesifik jika ada indikasi dari berita (bukan asumsi).
3. Soroti fenomena atau kejadian unik/tidak biasa yang menarik.
4. Bahasa Indonesia formal tapi tidak kaku.
5. Insight 3–5 kalimat. Langsung ke poin, tanpa basa-basi pembuka.
6. Jika berita kurang, tuliskan: "Data berita untuk periode ini belum mencukupi untuk analisis mendalam."
7. Pastikan berita yang diidentifikasi hanyalah pada scope daearah Kabupaten Tegal, jika ada di Kota Tegal boleh namun berikan sedikit warning.
"""

# ── Internal helpers ───────────────────────────────────────────────────────────

def _build_client() -> OpenAI:
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY tidak ditemukan di environment variables.")
    return OpenAI(api_key=api_key, base_url=_DEEPSEEK_BASE_URL)


def _prefilter_articles(articles: list[dict], category: str) -> list[dict]:
    """Filter artikel berdasarkan keyword kategori. Return semua jika hasil < 3."""
    keywords = _KEYWORDS.get(category, [])
    matched  = [
        a for a in articles
        if any(kw in f"{a.get('title','')} {a.get('tags','')} {a.get('content','')}".lower()
               for kw in keywords)
    ]
    return matched if len(matched) >= 3 else articles


def _get_sources(articles: list[dict], category: str) -> list[dict]:
    """
    Ambil daftar sumber berita acuan per kategori (maks _MAX_SOURCES_SHOWN).
    Return list {"title": ..., "url": ...}.
    """
    filtered = _prefilter_articles(articles, category)
    sources  = []
    seen     = set()
    for a in filtered:
        title = a.get("title", "").strip()
        url   = a.get("url", "").strip()
        if title and title not in seen:
            seen.add(title)
            sources.append({"title": title, "url": url})
        if len(sources) >= _MAX_SOURCES_SHOWN:
            break
    return sources


def _format_articles_for_prompt(articles: list[dict], category: str) -> str:
    """Format artikel menjadi teks ringkas untuk prompt LLM."""
    filtered = _prefilter_articles(articles, category)
    selected = filtered[:_MAX_ARTICLES_PER_CAT]

    if not selected:
        return "(Tidak ada berita yang relevan untuk periode ini)"

    lines = []
    for i, a in enumerate(selected, 1):
        title   = a.get("title", "").strip()
        date    = a.get("date", "").strip()
        tags    = a.get("tags", "").strip()
        content = (a.get("content", "") or "").strip()
        if len(content) > _MAX_CONTENT_CHARS:
            content = content[:_MAX_CONTENT_CHARS] + "..."

        parts = [f"{i}. [{date}] {title}"]
        if tags:
            parts.append(f"   Tags: {tags}")
        if content:
            parts.append(f"   Ringkasan: {content}")
        lines.append("\n".join(parts))

    return "\n\n".join(lines)


def _build_user_prompt(articles: list[dict], period_label: str) -> str:
    pdrb_text         = _format_articles_for_prompt(articles, "pdrb")
    kemiskinan_text   = _format_articles_for_prompt(articles, "kemiskinan")
    pengangguran_text = _format_articles_for_prompt(articles, "pengangguran")

    return f"""Berikut adalah berita lokal dari Kabupaten Tegal pada periode {period_label}.
Analisis dan berikan insight untuk masing-masing kategori.

Kembalikan HANYA JSON valid dengan format:
{{
  "pdrb": "<insight PDRB 3-5 kalimat>",
  "kemiskinan": "<insight Kemiskinan 3-5 kalimat>",
  "pengangguran": "<insight Pengangguran 3-5 kalimat>"
}}

---
### BERITA — PDRB & Ekonomi
{pdrb_text}

---
### BERITA — Kemiskinan & Kesejahteraan
{kemiskinan_text}

---
### BERITA — Pengangguran & Ketenagakerjaan
{pengangguran_text}
"""


def _extract_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Gagal mengekstrak JSON dari respons LLM: {raw[:300]}")


# ── Fungsi publik ──────────────────────────────────────────────────────────────

def generate_insights(articles: list[dict], period_label: str) -> dict:
    """
    Analisis daftar berita dengan DeepSeek. Return dict:
    {
        "pdrb":         str,
        "kemiskinan":   str,
        "pengangguran": str,
        "sources": {
            "pdrb":         [{"title": ..., "url": ...}, ...],
            "kemiskinan":   [...],
            "pengangguran": [...],
        }
    }
    """
    # Kumpulkan sumber berita per kategori (dilakukan di luar LLM, cepat)
    sources = {
        "pdrb":         _get_sources(articles, "pdrb"),
        "kemiskinan":   _get_sources(articles, "kemiskinan"),
        "pengangguran": _get_sources(articles, "pengangguran"),
    }

    if not articles:
        empty = "Tidak ada data berita untuk periode ini."
        return {
            "pdrb":         empty,
            "kemiskinan":   empty,
            "pengangguran": empty,
            "sources":      sources,
        }

    client      = _build_client()
    user_prompt = _build_user_prompt(articles, period_label)

    print(f"[AI Insights] Mengirim {len(articles)} artikel ke DeepSeek — {period_label}...")

    response = client.chat.completions.create(
        model=_DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.5,
        max_tokens=1200,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content or ""
    print(f"[AI Insights] Respons diterima ({len(raw)} karakter).")

    result = _extract_json(raw)

    for key in ("pdrb", "kemiskinan", "pengangguran"):
        if key not in result or not result[key]:
            result[key] = "Data berita periode ini belum mencukupi untuk analisis mendalam."

    result["sources"] = sources
    return result
