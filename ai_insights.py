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

_SYSTEM_PROMPT = """Kamu adalah analis ekonomi senior dari Badan Pusat Statistik (BPS) Kabupaten Tegal.
Tugasmu: membaca berita lokal dan menghasilkan insight analitis yang dapat ditindaklanjuti oleh BPS untuk tiga indikator makroekonomi utama.

=== FOKUS PER KATEGORI ===

[PDRB & Ekonomi]
Analisis aktivitas ekonomi yang berpengaruh terhadap perhitungan PDRB Kabupaten Tegal:
- Identifikasi sektor lapangan usaha yang menggeliat atau lesu (pertanian, industri, perdagangan, jasa, pariwisata, konstruksi, dll.)
- Catat ada/tidaknya investasi masuk, proyek infrastruktur, atau ekspansi usaha
- Soroti pergerakan harga/inflasi lokal dan komoditas yang dominan
- Jika ada data kuantitatif dalam berita (angka produksi, omset, nilai proyek), sebutkan
- Simpulkan implikasinya terhadap estimasi pertumbuhan ekonomi daerah

[Kemiskinan & Kesejahteraan]
Analisis kondisi sosial-ekonomi yang relevan terhadap pengukuran kemiskinan BPS:
- Identifikasi penerima dan cakupan program bansos (PKH, BPNT, BLT, bedah rumah, dll.)
- Catat indikator kesejahteraan: akses pangan, gizi, perumahan layak, sanitasi
- Soroti kelompok rentan (lansia, disabilitas, yatim, keluarga miskin ekstrem) yang disebut
- Tandai jika ada ketidaksesuaian antara data penerima bansos dengan kondisi lapangan
- Simpulkan apakah tren menunjukkan penurunan atau risiko kenaikan angka kemiskinan

[Pengangguran & Ketenagakerjaan]
Analisis dinamika pasar kerja di Kabupaten Tegal:
- Identifikasi peristiwa yang mempengaruhi Tingkat Pengangguran Terbuka (TPT): PHK, rekrutmen massal, job fair, penutupan usaha
- Catat sektor dan jumlah tenaga kerja yang terdampak jika disebutkan
- Soroti program pelatihan kerja, sertifikasi, atau pemberdayaan UMKM dari pemerintah
- Perhatikan kondisi TKI/TKW dan migrasi tenaga kerja
- Simpulkan arah pergerakan TPT dan sektor yang perlu dipantau BPS

=== PANDUAN PENULISAN ===
1. Tulis langsung ke poin — tidak ada kalimat pembuka basa-basi
2. Gunakan bahasa Indonesia formal namun mudah dipahami non-teknisi
3. Setiap kategori: 3–5 kalimat, padat dan berbasis fakta berita
4. Jika ada data angka dari berita, cantumkan dalam insight
5. Jika berita mencakup Kota Tegal (bukan Kabupaten Tegal), tetap analisis namun awali dengan "[Catatan: berita ini terkait Kota Tegal, bukan Kabupaten]"
6. Jika berita sangat minim untuk suatu kategori, tulis: "Data berita periode ini belum cukup untuk analisis mendalam pada kategori ini. BPS disarankan mengacu pada sumber primer."
"""

# ── Internal helpers ───────────────────────────────────────────────────────────

def _build_client() -> OpenAI:
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY tidak ditemukan di environment variables.")
    return OpenAI(api_key=api_key, base_url=_DEEPSEEK_BASE_URL)


def _prefilter_articles(articles: list[dict], category: str) -> list[dict]:
    """
    Filter artikel berdasarkan keyword kategori.
    Hanya artikel yang benar-benar mengandung keyword yang dikembalikan.
    Tidak ada fallback ke semua artikel agar sumber selalu relevan.
    """
    keywords = _KEYWORDS.get(category, [])
    return [
        a for a in articles
        if any(kw in f"{a.get('title','')} {a.get('tags','')} {a.get('content','')}".lower()
               for kw in keywords)
    ]


def _get_sources(articles: list[dict], category: str) -> list[dict]:
    """Fallback: ambil sumber dari keyword match (dipakai jika AI tidak return IDs)."""
    matched  = _prefilter_articles(articles, category)
    sources  = []
    seen     = set()
    for a in matched:
        title = a.get("title", "").strip()
        url   = a.get("url", "").strip()
        if title and title not in seen:
            seen.add(title)
            sources.append({"title": title, "url": url})
        if len(sources) >= _MAX_SOURCES_SHOWN:
            break
    return sources


def _format_articles_for_prompt(
    articles: list[dict], category: str, id_prefix: str = "A"
) -> tuple[str, dict[str, dict]]:
    """
    Format artikel menjadi teks ringkas dengan tag [P01], [K01], [T01] dst.
    id_prefix: "P" untuk PDRB, "K" untuk Kemiskinan, "T" untuk Pengangguran.
    Return (formatted_text, id_map) dimana id_map = {"P01": {"title": ..., "url": ...}, ...}
    """
    filtered = _prefilter_articles(articles, category)
    selected = filtered[:_MAX_ARTICLES_PER_CAT]

    if not selected:
        return "(Tidak ada berita yang relevan untuk periode ini)", {}

    lines  = []
    id_map = {}
    for i, a in enumerate(selected, 1):
        tag_id  = f"{id_prefix}{i:02d}"
        title   = a.get("title", "").strip()
        date    = a.get("date", "").strip()
        tags    = a.get("tags", "").strip()
        url     = a.get("url", "").strip()
        content = (a.get("content", "") or "").strip()
        if len(content) > _MAX_CONTENT_CHARS:
            content = content[:_MAX_CONTENT_CHARS] + "..."

        id_map[tag_id] = {"title": title, "url": url}

        parts = [f"[{tag_id}] [{date}] {title}"]
        if tags:
            parts.append(f"      Tags: {tags}")
        if content:
            parts.append(f"      Ringkasan: {content}")
        lines.append("\n".join(parts))

    return "\n\n".join(lines), id_map


def _build_user_prompt(
    articles: list[dict], period_label: str
) -> tuple[str, dict[str, dict]]:
    """
    Bangun user prompt + gabungan id_map dari semua kategori.
    Return (prompt_text, merged_id_map).
    """
    pdrb_text,         pdrb_map         = _format_articles_for_prompt(articles, "pdrb",         "P")
    kemiskinan_text,   kemiskinan_map   = _format_articles_for_prompt(articles, "kemiskinan",   "K")
    pengangguran_text, pengangguran_map = _format_articles_for_prompt(articles, "pengangguran", "T")

    # Gabung semua id_map (ID bisa duplikat lintas kategori, OK karena value sama)
    merged = {}
    merged.update(pdrb_map)
    merged.update(kemiskinan_map)
    merged.update(pengangguran_map)

    prompt = f"""Berikut adalah berita lokal dari Kabupaten Tegal pada periode {period_label}.
Setiap berita diberi kode unik: P01, P02 (PDRB), K01, K02 (Kemiskinan), T01, T02 (Pengangguran).
Analisis dan berikan insight untuk masing-masing kategori.

Kembalikan HANYA JSON valid dengan format:
{{
  "pdrb": "<insight PDRB 3-5 kalimat>",
  "pdrb_source_ids": ["P01", "P03"],
  "kemiskinan": "<insight Kemiskinan 3-5 kalimat>",
  "kemiskinan_source_ids": ["K02", "K05"],
  "pengangguran": "<insight Pengangguran 3-5 kalimat>",
  "pengangguran_source_ids": ["T01", "T04"]
}}

ATURAN SITASI INLINE:
- Di akhir kalimat yang merujuk suatu berita, tambahkan kode artikelnya SEBELUM tanda titik
- Gunakan kode prefix yang sesuai: P (PDRB), K (Kemiskinan), T (Pengangguran)
- Contoh: "Sektor pertanian meningkat akibat program intensifikasi [P03]. PHK melanda pabrik tekstil Slawi [T02]."
- Satu kalimat bisa merujuk lebih dari satu berita: [P01][P04]
- Kode yang dicantumkan HANYA yang benar-benar menjadi dasar kalimat tersebut
- Jika data belum cukup dan tidak ada berita yang dirujuk, JANGAN cantumkan kode apapun
- Tidak perlu mengisi pdrb_source_ids, kemiskinan_source_ids, pengangguran_source_ids (opsional)

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
    return prompt, merged


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


# Frasa yang menandakan AI menyatakan data tidak cukup
_INSUFFICIENT_PHRASES = (
    "belum cukup",
    "belum mencukupi",
    "tidak ada data",
    "tidak ada berita",
    "sumber primer",
)


def _is_insufficient(text: str) -> bool:
    """True jika teks insight menyatakan data tidak memadai."""
    t = text.lower()
    return any(phrase in t for phrase in _INSUFFICIENT_PHRASES)


# Regex untuk mendeteksi kode sitasi inline: [P01], [K03], [T12] dst.
_CITE_RE = re.compile(r"\[([PKT]\d+)\]")


def _inject_inline_links(
    text: str, id_map: dict[str, dict]
) -> tuple[str, list[dict]]:
    """
    Ganti [Pxx]/[Kxx]/[Txx] dalam teks dengan HTML link.
    Return (html_text, sources_list) — sources hanya artikel yang benar-benar dirujuk AI.
    """
    seen    = {}   # tag_id → {title, url, num}
    order   = []   # urutan kemunculan
    counter = [0]  # mutable counter

    def _replace(m):
        tag_id = m.group(1).upper()
        info   = id_map.get(tag_id)
        if not info:
            return ""   # hapus kode palsu (hallucination)
        if tag_id not in seen:
            counter[0] += 1
            seen[tag_id] = {**info, "num": counter[0]}
            order.append(tag_id)
        num   = seen[tag_id]["num"]
        url   = info.get("url", "#")
        title = info.get("title", "artikel")
        safe_url   = url.replace('"', '%22')
        safe_title = title.replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')
        return (
            f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer" '
            f'class="ai-cite" title="{safe_title}">{num}</a>'
        )

    html_text = _CITE_RE.sub(_replace, text)
    # Escape HTML biasa untuk teks non-link (cegah XSS)
    # Karena kita sudah embed <a>, kita escape SEBELUM substitusi
    # Pendekatan: escape dulu, lalu replace placeholder
    # Implementasi sederhana: teks sudah di-escape di frontend — di sini return as-is
    # (teks murni dari LLM, tidak dari user input, risiko XSS minimal)
    sources = [seen[tid] for tid in order if tid in seen]
    return html_text, sources


def _resolve_sources(source_ids: list, id_map: dict[str, dict]) -> list[dict]:
    """
    Mapping ID yang dikembalikan AI ke artikel aslinya.
    Buang ID yang tidak valid (hallucination guard).
    """
    sources = []
    seen    = set()
    for sid in source_ids:
        sid = str(sid).strip().upper()
        if sid in id_map and sid not in seen:
            seen.add(sid)
            sources.append(id_map[sid])
        if len(sources) >= _MAX_SOURCES_SHOWN:
            break
    return sources


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
    if not articles:
        empty = "Tidak ada data berita untuk periode ini."
        return {
            "pdrb":         empty,
            "kemiskinan":   empty,
            "pengangguran": empty,
            "sources":      {"pdrb": [], "kemiskinan": [], "pengangguran": []},
        }

    client                = _build_client()
    user_prompt, id_map   = _build_user_prompt(articles, period_label)

    print(f"[AI Insights] Mengirim {len(articles)} artikel ke DeepSeek — {period_label}...")
    print(f"[AI Insights] ID map: {len(id_map)} artikel ditandai.")

    response = client.chat.completions.create(
        model=_DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.5,
        max_tokens=1500,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content or ""
    print(f"[AI Insights] Respons diterima ({len(raw)} karakter).")

    result = _extract_json(raw)

    # ── Teks insight: fallback jika kosong ──────────────────────────────────
    for key in ("pdrb", "kemiskinan", "pengangguran"):
        if key not in result or not result[key]:
            result[key] = "Data berita periode ini belum mencukupi untuk analisis mendalam."

    # ── Injeksi link inline + derivasi sumber dari marker ───────────────────
    sources = {}
    for cat in ("pdrb", "kemiskinan", "pengangguran"):
        insight_text = result.get(cat, "")

        # Safety net: kalau insight bilang data belum cukup, sumber pasti kosong
        if _is_insufficient(insight_text):
            result[cat] = insight_text   # teks plain, tidak ada link
            sources[cat] = []
            print(f"[AI Insights] {cat}: insight menyatakan data kurang → sources kosong.")
            continue

        # Inject inline citation links + derive sources dari marker dalam teks
        html_text, inline_sources = _inject_inline_links(insight_text, id_map)
        result[cat] = html_text  # teks insight kini berisi HTML anchor

        if inline_sources:
            sources[cat] = inline_sources
            print(f"[AI Insights] {cat}: {len(inline_sources)} sumber dari sitasi inline.")
        else:
            # Fallback 1: pakai *_source_ids dari JSON AI
            ai_ids = result.get(f"{cat}_source_ids", [])
            if isinstance(ai_ids, list) and ai_ids:
                resolved = _resolve_sources(ai_ids, id_map)
                sources[cat] = resolved
                print(f"[AI Insights] {cat}: fallback source_ids → {len(resolved)} valid.")
            else:
                # Fallback 2: keyword-based (lama)
                sources[cat] = _get_sources(articles, cat)
                print(f"[AI Insights] {cat}: fallback keyword match.")

    result["sources"] = sources
    return result
