"""
ai_insights.py — Modul AI Insight menggunakan DeepSeek LLM + RAG (pgvector)

Menganalisis berita dari database dan menghasilkan insight untuk tiga kategori:
PDRB, Kemiskinan, dan Pengangguran.

Alur RAG:
  1. Semantic search via pgvector (text-embedding-3-small) per kategori
  2. Artikel top-K paling relevan dikirim ke DeepSeek sebagai konteks
  3. Fallback ke keyword filtering jika embedding belum tersedia
"""

import json
import os
import re

from openai import OpenAI

from embeddings import semantic_search_multi

# ── Konstanta ──────────────────────────────────────────────────────────────────

_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
_DEEPSEEK_MODEL    = "deepseek-chat"

# Jumlah karakter konten per artikel yang dikirim ke LLM
# Dinaikkan dari 500 → 800 karena artikel sudah di-filter by relevance
_MAX_CONTENT_CHARS     = 800
# Maks artikel per kategori yang dikirim ke LLM
_MAX_ARTICLES_PER_CAT  = 30
# Maks sumber yang ditampilkan ke user per kategori
_MAX_SOURCES_SHOWN     = 6
# Minimum artikel dari semantic search sebelum fallback ke keyword
_MIN_SEMANTIC_RESULTS  = 5

# ── Semantic query templates per kategori ─────────────────────────────────────
# Query ini di-embed dan dipakai untuk vector search di pgvector.
# Ditulis dalam Bahasa Indonesia agar cosine similarity lebih tepat.

_SEMANTIC_QUERIES: dict[str, str] = {
    "pdrb": (
        "aktivitas ekonomi PDRB pertumbuhan sektor industri perdagangan investasi "
        "infrastruktur proyek pertanian pariwisata manufaktur UMKM omset pendapatan "
        "inflasi harga komoditas fiskal anggaran ekspor impor Kabupaten Tegal"
    ),
    "kemiskinan": (
        "kemiskinan bantuan sosial kesejahteraan masyarakat miskin program PKH BLT "
        "BPNT sembako stunting gizi buruk bedah rumah rumah layak huni kelompok rentan "
        "lansia disabilitas yatim pengentasan kemiskinan data BPS Kabupaten Tegal"
    ),
    "pengangguran": (
        "pengangguran ketenagakerjaan PHK pemutusan hubungan kerja lapangan kerja "
        "buruh tenaga kerja rekrutmen job fair lowongan pelatihan kerja disnaker "
        "TKI TKW upah minimum TPT tingkat pengangguran terbuka Kabupaten Tegal"
    ),
}

# Keyword per kategori — untuk fallback jika semantic search gagal/kurang
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
    Keyword-based filter — dipakai sebagai FALLBACK jika semantic search
    gagal atau return terlalu sedikit artikel.
    """
    keywords = _KEYWORDS.get(category, [])
    return [
        a for a in articles
        if any(kw in f"{a.get('title','')} {a.get('tags','')} {a.get('content','')}".lower()
               for kw in keywords)
    ]


def _get_sources(articles: list[dict], category: str) -> list[dict]:
    """Fallback: ambil sumber dari keyword match (dipakai jika AI tidak return IDs)."""
    matched = _prefilter_articles(articles, category)
    sources = []
    seen    = set()
    for a in matched:
        title = a.get("title", "").strip()
        url   = a.get("url", "").strip()
        if title and title not in seen:
            seen.add(title)
            sources.append({"title": title, "url": url})
        if len(sources) >= _MAX_SOURCES_SHOWN:
            break
    return sources


def _select_articles_for_category(
    category:          str,
    semantic_results:  dict[str, list[dict]],
    fallback_articles: list[dict],
) -> list[dict]:
    """
    Pilih artikel untuk suatu kategori dengan prioritas:
    1. Hasil semantic search (sudah di-rank by similarity)
    2. Fallback keyword filter dari fallback_articles (jika semantic < _MIN_SEMANTIC_RESULTS)

    Return list artikel siap dipakai, maks _MAX_ARTICLES_PER_CAT.
    """
    semantic_hits = semantic_results.get(category, [])

    if len(semantic_hits) >= _MIN_SEMANTIC_RESULTS:
        selected = semantic_hits[:_MAX_ARTICLES_PER_CAT]
        print(
            f"[AI Insights] {category}: {len(selected)} artikel dari semantic search "
            f"(similarity tertinggi: {selected[0].get('similarity', 0):.3f})"
            if selected else f"[AI Insights] {category}: 0 artikel."
        )
        return selected

    # Fallback: keyword match dari artikel yang di-pass
    print(
        f"[AI Insights] {category}: semantic search hanya dapat {len(semantic_hits)} artikel "
        f"(< {_MIN_SEMANTIC_RESULTS}) - fallback ke keyword filter."
    )
    keyword_hits = _prefilter_articles(fallback_articles, category)
    # Gabung: semantic hits dulu, lalu keyword hits yang belum ada
    seen_urls    = {a.get("url") for a in semantic_hits}
    extra        = [a for a in keyword_hits if a.get("url") not in seen_urls]
    combined     = (semantic_hits + extra)[:_MAX_ARTICLES_PER_CAT]
    print(f"[AI Insights] {category}: fallback - total {len(combined)} artikel.")
    return combined


def _format_articles_for_prompt(
    articles: list[dict], id_prefix: str = "A"
) -> tuple[str, dict[str, dict]]:
    """
    Format artikel menjadi teks ringkas dengan tag [P01], [K01], [T01] dst.
    id_prefix: "P" untuk PDRB, "K" untuk Kemiskinan, "T" untuk Pengangguran.
    Return (formatted_text, id_map) dimana id_map = {"P01": {"title": ..., "url": ...}, ...}

    Artikel sudah diurutkan by relevance (dari semantic search) — paling relevan di atas.
    """
    if not articles:
        return "(Tidak ada berita yang relevan untuk periode ini)", {}

    lines  = []
    id_map = {}
    for i, a in enumerate(articles, 1):
        tag_id     = f"{id_prefix}{i:02d}"
        title      = a.get("title", "").strip()
        date       = a.get("date", "").strip()
        tags       = a.get("tags", "").strip()
        url        = a.get("url", "").strip()
        content    = (a.get("content", "") or "").strip()
        similarity = a.get("similarity")   # ada jika dari semantic search

        if len(content) > _MAX_CONTENT_CHARS:
            content = content[:_MAX_CONTENT_CHARS] + "..."

        id_map[tag_id] = {"title": title, "url": url}

        parts = [f"[{tag_id}] [{date}] {title}"]
        # Tambahkan label relevansi jika data similarity tersedia
        if similarity is not None:
            label = "Tinggi" if similarity >= 0.5 else ("Sedang" if similarity >= 0.3 else "Rendah")
            parts[0] += f"  ·  Relevansi: {label} ({similarity:.2f})"
        if tags:
            parts.append(f"      Tags: {tags}")
        if content:
            parts.append(f"      Ringkasan: {content}")
        lines.append("\n".join(parts))

    return "\n\n".join(lines), id_map


def _build_user_prompt(
    pdrb_articles:         list[dict],
    kemiskinan_articles:   list[dict],
    pengangguran_articles: list[dict],
    period_label:          str,
) -> tuple[str, dict[str, dict]]:
    """
    Bangun user prompt + gabungan id_map dari semua kategori.
    Return (prompt_text, merged_id_map).
    """
    pdrb_text,         pdrb_map         = _format_articles_for_prompt(pdrb_articles,         "P")
    kemiskinan_text,   kemiskinan_map   = _format_articles_for_prompt(kemiskinan_articles,   "K")
    pengangguran_text, pengangguran_map = _format_articles_for_prompt(pengangguran_articles, "T")

    # Gabung semua id_map
    merged = {}
    merged.update(pdrb_map)
    merged.update(kemiskinan_map)
    merged.update(pengangguran_map)

    prompt = f"""Berikut adalah berita lokal dari Kabupaten Tegal pada periode {period_label}.
Setiap berita diberi kode unik: P01, P02 (PDRB), K01, K02 (Kemiskinan), T01, T02 (Pengangguran).
Berita sudah diurutkan berdasarkan relevansi — yang teratas paling relevan untuk kategorinya.
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
        num        = seen[tag_id]["num"]
        url        = info.get("url", "#")
        title      = info.get("title", "artikel")
        safe_url   = url.replace('"', '%22')
        safe_title = title.replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')
        return (
            f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer" '
            f'class="ai-cite" title="{safe_title}">{num}</a>'
        )

    html_text = _CITE_RE.sub(_replace, text)
    sources   = [seen[tid] for tid in order if tid in seen]
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


# ── Main entry point ───────────────────────────────────────────────────────────

def generate_insights(
    period_label:      str,
    date_from:         str | None    = None,
    date_to:           str | None    = None,
    supabase_client                  = None,
    articles:          list[dict] | None = None,
) -> dict:
    """
    Analisis berita dengan DeepSeek menggunakan RAG (pgvector semantic search).

    Alur utama (jika date_from + date_to + supabase_client tersedia):
      1. Semantic search per kategori via pgvector → top-30 artikel paling relevan
      2. Format artikel → kirim ke DeepSeek dengan konteks yang sudah di-rank
      3. Inject inline citation links ke hasil insight

    Fallback (jika semantic search gagal atau embedding belum ada):
      - Gunakan articles list (keyword-based filter)

    Args:
      period_label:    Label periode, misal "Triwulan I 2026 (Jan–Mar)"
      date_from:       Filter tanggal dari (YYYY-MM-DD), opsional
      date_to:         Filter tanggal sampai (YYYY-MM-DD), opsional
      supabase_client: Instance supabase-py untuk RPC call, opsional
      articles:        Fallback articles list (dari _fetch_period_articles), opsional

    Return dict:
      {"pdrb": str, "kemiskinan": str, "pengangguran": str,
       "sources": {"pdrb": [...], "kemiskinan": [...], "pengangguran": [...]}}
    """
    fallback_articles = articles or []
    semantic_results  = {}

    # ── Semantic search via pgvector ──────────────────────────────────────────
    use_semantic = (
        supabase_client is not None
        and date_from is not None
        and date_to is not None
    )

    if use_semantic:
        print(f"[AI Insights] Menjalankan semantic search untuk periode {period_label}...")
        try:
            semantic_results = semantic_search_multi(
                queries         = _SEMANTIC_QUERIES,
                supabase_client = supabase_client,
                date_from       = date_from,
                date_to         = date_to,
                top_k           = _MAX_ARTICLES_PER_CAT,
                min_similarity  = 0.1,
            )
        except Exception as exc:
            print(f"[AI Insights] Semantic search gagal: {exc} -> fallback ke keyword.")
            semantic_results = {}
    else:
        print(f"[AI Insights] Semantic search tidak tersedia - fallback ke keyword filter.")

    # ── Pilih artikel per kategori (semantic + fallback) ──────────────────────
    pdrb_articles         = _select_articles_for_category("pdrb",         semantic_results, fallback_articles)
    kemiskinan_articles   = _select_articles_for_category("kemiskinan",   semantic_results, fallback_articles)
    pengangguran_articles = _select_articles_for_category("pengangguran", semantic_results, fallback_articles)

    # Cek apakah semua kategori kosong
    total_articles = len(pdrb_articles) + len(kemiskinan_articles) + len(pengangguran_articles)
    if total_articles == 0:
        empty = "Tidak ada data berita untuk periode ini."
        return {
            "pdrb":         empty,
            "kemiskinan":   empty,
            "pengangguran": empty,
            "sources":      {"pdrb": [], "kemiskinan": [], "pengangguran": []},
        }

    print(
        f"[AI Insights] Konteks yang akan dikirim ke LLM: "
        f"PDRB={len(pdrb_articles)}, "
        f"Kemiskinan={len(kemiskinan_articles)}, "
        f"Pengangguran={len(pengangguran_articles)} artikel."
    )

    # ── Build prompt dan kirim ke DeepSeek ────────────────────────────────────
    client                  = _build_client()
    user_prompt, id_map     = _build_user_prompt(
        pdrb_articles, kemiskinan_articles, pengangguran_articles, period_label
    )

    print(f"[AI Insights] Mengirim konteks ke DeepSeek — {period_label}...")
    print(f"[AI Insights] ID map: {len(id_map)} artikel ditandai.")

    response = client.chat.completions.create(
        model=_DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.4,      # Sedikit lebih rendah dari sebelumnya (0.5) → lebih konsisten
        max_tokens=2000,      # Dinaikkan dari 1500 → ruang lebih untuk insight mendalam
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content or ""
    print(f"[AI Insights] Respons diterima ({len(raw)} karakter).")

    result = _extract_json(raw)

    # ── Teks insight: fallback jika kosong ────────────────────────────────────
    for key in ("pdrb", "kemiskinan", "pengangguran"):
        if key not in result or not result[key]:
            result[key] = "Data berita periode ini belum mencukupi untuk analisis mendalam."

    # ── Injeksi link inline + derivasi sumber dari marker ────────────────────
    # Siapkan all_articles untuk fallback keyword-based sources
    all_category_articles = {
        "pdrb":         pdrb_articles,
        "kemiskinan":   kemiskinan_articles,
        "pengangguran": pengangguran_articles,
    }

    sources = {}
    for cat in ("pdrb", "kemiskinan", "pengangguran"):
        insight_text = result.get(cat, "")

        # Selalu inject inline links, bahkan jika insight bilang data kurang
        # karena AI mungkin tetap merujuk berita dengan sitasi [P01], [K02], dll.
        html_text, inline_sources = _inject_inline_links(insight_text, id_map)
        result[cat] = html_text

        if inline_sources:
            sources[cat] = inline_sources
            print(f"[AI Insights] {cat}: {len(inline_sources)} sumber dari sitasi inline.")
        elif not _is_insufficient(insight_text):
            # Hanya fallback jika insight TIDAK menyatakan data kurang
            # Fallback 1: pakai *_source_ids dari JSON AI
            ai_ids = result.get(f"{cat}_source_ids", [])
            if isinstance(ai_ids, list) and ai_ids:
                resolved    = _resolve_sources(ai_ids, id_map)
                sources[cat] = resolved
                print(f"[AI Insights] {cat}: fallback source_ids - {len(resolved)} valid.")
            else:
                # Fallback 2: keyword-based dari artikel kategori yang sudah dipilih
                sources[cat] = _get_sources(all_category_articles[cat], cat)
                print(f"[AI Insights] {cat}: fallback keyword match.")
        else:
            # Insight menyatakan data kurang dan tidak ada inline citations
            sources[cat] = []
            print(f"[AI Insights] {cat}: insight menyatakan data kurang, tidak ada sitasi.")

    result["sources"] = sources
    return result
