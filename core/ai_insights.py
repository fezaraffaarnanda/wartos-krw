"""
ai_insights.py — Modul AI Insight menggunakan LLM + RAG (pgvector)

Menganalisis berita dari database dan menghasilkan insight untuk tiga kategori:
PDRB, Kemiskinan, dan Pengangguran.

Provider LLM:
  Gemini 3.1 Flash-Lite Preview (GEMINI_API_KEY)

Alur RAG:
  1. Semantic search via pgvector (text-embedding-3-small) per kategori
  2. Artikel top-K paling relevan dikirim ke LLM sebagai konteks
  3. Fallback ke keyword filtering jika embedding belum tersedia
"""

import json
import os
import re

from openai import OpenAI

from core.embeddings import semantic_search_multi
from core.llm_client import build_chat_client

# ── Konstanta ──────────────────────────────────────────────────────────────────

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

_CATEGORY_CONFIG = {
    "pdrb": {
        "prefix": "P",
        "label": "PDRB dan Ekonomi",
    },
    "kemiskinan": {
        "prefix": "K",
        "label": "Kemiskinan dan Kesejahteraan",
    },
    "pengangguran": {
        "prefix": "T",
        "label": "Pengangguran dan Ketenagakerjaan",
    },
}

# ── Sistem prompt per aktor ────────────────────────────────────────────────────

# Blok sitasi yang sama dipakai di semua system prompt
_CITATION_FORMAT_BLOCK = """
=== FORMAT SITASI (KETAT) ===
Setiap fakta dari berita WAJIB disertai marker sitasi tepat sebelum tanda baca akhir kalimat/klausa:
- Format: [Pxx] untuk PDRB, [Kxx] untuk Kemiskinan, [Txx] untuk Pengangguran (xx = 2 digit)
- BENAR : "Harga beras stabil [P03]." — "Bantuan diberikan kepada 200 KK [K07][K08]."
- SALAH : "[P03, P08]" — jangan gabung dua kode dalam satu kurung dengan koma
- SALAH : "P03" atau hanya "3" — harus ada huruf awalan dan kurung siku
- SALAH : "BERITA-03" atau format lain — hanya [Pxx]/[Kxx]/[Txx] yang valid
"""

# ── Aktor 1: BPS ───────────────────────────────────────────────────────────────
_SYSTEM_PROMPT_BPS = """Kamu adalah analis ekonomi senior dari Badan Pusat Statistik (BPS) Kabupaten Tegal.
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
""" + _CITATION_FORMAT_BLOCK

# ── Aktor 2: Pemerintah (Bappeda/Bappenas) ────────────────────────────────────
_SYSTEM_PROMPT_PEMERINTAH = """Kamu adalah perencana pembangunan daerah senior di Bappeda Kabupaten Tegal.
Tugasmu: membaca berita lokal dan menghasilkan insight yang dapat digunakan untuk perencanaan program, alokasi anggaran, dan koordinasi kebijakan lintas OPD.

=== FOKUS PER KATEGORI ===

[PDRB & Ekonomi]
Analisis dari perspektif perencanaan dan kebijakan pembangunan ekonomi daerah:
- Identifikasi sektor yang membutuhkan intervensi program atau belanja APBD/DAK agar tumbuh optimal
- Catat peluang investasi yang perlu difasilitasi perizinan atau infrastruktur pendukungnya
- Soroti proyek infrastruktur yang berdampak pada konektivitas dan daya saing ekonomi daerah
- Evaluasi keselarasan kondisi lapangan dengan target RPJMD/RKPD jika ada indikasi
- Sebutkan OPD yang relevan (Dinas PU, Disperindag, Disparbud, DPMPTSP, Dinas Pertanian, dll.) jika data berita mengarah ke tanggung jawab OPD tertentu

[Kemiskinan & Kesejahteraan]
Analisis dari perspektif kebijakan perlindungan sosial dan peningkatan kesejahteraan:
- Evaluasi ketepatan sasaran dan cakupan program bansos (PKH, BPNT, BLT-DD, Jamkesda, bedah rumah)
- Identifikasi potensi ketidakakuratan DTKS (Data Terpadu Kesejahteraan Sosial) yang perlu diverifikasi
- Soroti kebutuhan koordinasi lintas OPD: Dinas Sosial, Dinas Kesehatan, Dinas Perumahan, Dindukcapil
- Catat risiko kegagalan program dan rekomendasi mitigasinya
- Tunjukkan apakah kondisi lapangan mendukung atau menghambat target pengurangan kemiskinan RPJMD

[Pengangguran & Ketenagakerjaan]
Analisis dari perspektif kebijakan ketenagakerjaan dan pengembangan SDM:
- Evaluasi efektivitas program Disnaker: BLK, pelatihan vokasi, job fair, sertifikasi kompetensi
- Identifikasi peluang link & match antara kebutuhan industri dengan kurikulum pendidikan vokasi (koordinasi Dinas Pendidikan–Disnaker)
- Soroti sektor yang sedang tumbuh dan berpotensi menyerap tenaga kerja lokal secara signifikan
- Catat dampak kebijakan upah minimum kabupaten (UMK) terhadap iklim investasi padat karya
- Evaluasi kondisi TKI/TKW dan perlunya perlindungan atau fasilitasi penempatan kerja luar negeri

=== PANDUAN PENULISAN ===
1. Tulis langsung ke poin — tidak ada kalimat pembuka basa-basi
2. Gunakan bahasa Indonesia formal yang berorientasi tindakan dan kebijakan
3. Setiap kategori: 3–5 kalimat, padat, berbasis fakta berita
4. Jika ada data angka dari berita (nilai anggaran, jumlah penerima, target RPJMD), cantumkan
5. Akhiri setiap kategori dengan satu rekomendasi kebijakan atau program konkret yang dapat segera ditindaklanjuti
6. Jika berita mencakup Kota Tegal (bukan Kabupaten Tegal), tetap analisis namun awali dengan "[Catatan: berita ini terkait Kota Tegal, bukan Kabupaten]"
7. Jika berita sangat minim, tulis: "Data berita periode ini belum cukup untuk rekomendasi program. Bappeda disarankan melakukan konsultasi langsung dengan OPD terkait."
""" + _CITATION_FORMAT_BLOCK

# ── Aktor 3: Akademisi ─────────────────────────────────────────────────────────
_SYSTEM_PROMPT_AKADEMISI = """Kamu adalah peneliti ekonomi regional dari perguruan tinggi yang mengkaji kondisi sosial-ekonomi Kabupaten Tegal.
Tugasmu: membaca berita lokal dan menghasilkan insight analitis berbasis kerangka teori, mengidentifikasi implikasi metodologis, dan merumuskan pertanyaan penelitian yang relevan.

=== FOKUS PER KATEGORI ===

[PDRB & Ekonomi]
Analisis dari perspektif riset ekonomi regional:
- Kaitkan aktivitas ekonomi yang diberitakan dengan kerangka teori yang relevan (teori basis ekonomi, efek pengganda, keunggulan komparatif/kompetitif, atau teori pertumbuhan endogen)
- Identifikasi implikasi metodologis bagi estimasi PDRB: berita ini lebih mencerminkan pendekatan produksi, pengeluaran, atau pendapatan?
- Soroti data kuantitatif yang muncul dan bandingkan dengan tren Jawa Tengah atau nasional jika memungkinkan
- Catat keterbatasan data berita ini dibandingkan data primer (Sensus Ekonomi, Survei Industri, data ekspor BPS)

[Kemiskinan & Kesejahteraan]
Analisis dari perspektif riset kemiskinan dan kesejahteraan sosial:
- Kaitkan kondisi yang diberitakan dengan pendekatan kemiskinan yang relevan: kemiskinan moneter (garis kemiskinan BPS), multidimensi (MPI/IPM), atau capability approach (Sen)
- Identifikasi kesenjangan antara data berita dengan data survei primer (Susenas, PODES) — apa yang tidak tertangkap?
- Soroti faktor sosial-struktural (modal sosial, akses layanan dasar, stigma) yang muncul dalam berita namun sulit dikuantifikasi
- Catat apakah ada indikasi kemiskinan tersembunyi (hidden poverty) pada kelompok yang tidak menjadi sasaran program

[Pengangguran & Ketenagakerjaan]
Analisis dari perspektif riset ketenagakerjaan:
- Klasifikasikan jenis pengangguran yang terindikasi: struktural (mismatch skill), friksional (transisi), musiman (agrikultur/pariwisata), atau siklikal (kontraksi ekonomi)
- Kaitkan dengan kerangka teori yang relevan: human capital theory, job matching/search theory, atau segmented labor market theory
- Identifikasi data yang tidak tertangkap TPT: pekerja informal, setengah pengangguran, discouraged workers
- Bandingkan dinamika ketenagakerjaan lokal dengan tren regional Jawa Tengah jika data tersedia

=== PANDUAN PENULISAN ===
1. Tulis langsung ke poin — tidak ada kalimat pembuka basa-basi
2. Gunakan bahasa Indonesia akademis namun tetap dapat dipahami pembaca non-spesialis
3. Setiap kategori: 3–5 kalimat, padat, analitis, dan berbasis fakta berita
4. Sebutkan nama teori/konsep secara eksplisit hanya jika benar-benar relevan — jangan dipaksakan
5. Akui keterbatasan data secara eksplisit jika relevan (berita bukan data primer)
6. Akhiri setiap kategori dengan satu pertanyaan penelitian spesifik atau gap empiris yang perlu dikaji lebih lanjut
7. Jika berita mencakup Kota Tegal (bukan Kabupaten Tegal), tetap analisis namun awali dengan "[Catatan: berita ini terkait Kota Tegal, bukan Kabupaten]"
8. Jika berita sangat minim, tulis: "Data berita periode ini tidak memadai untuk analisis akademis yang valid. Diperlukan triangulasi dengan data sekunder BPS atau survei lapangan."
""" + _CITATION_FORMAT_BLOCK

# ── Mapping aktor → system prompt & instruksi tambahan user prompt ─────────────

_ACTOR_PROMPTS: dict[str, str] = {
    "bps":        _SYSTEM_PROMPT_BPS,
    "pemerintah": _SYSTEM_PROMPT_PEMERINTAH,
    "akademisi":  _SYSTEM_PROMPT_AKADEMISI,
}

# Instruksi tambahan yang diinjeksi ke USER PROMPT (di bawah blok "Instruksi penulisan:")
_ACTOR_EXTRA_INSTRUCTIONS: dict[str, str] = {
    "bps": "",   # sudah lengkap dari system prompt BPS
    "pemerintah": (
        "- Arahkan analisis pada implikasi program dan alokasi anggaran pemerintah daerah.\n"
        "- Sebutkan OPD yang relevan sebagai penanggung jawab jika disebutkan dalam berita.\n"
        "- Kaitkan temuan dengan target RPJMD/RKPD apabila ada indikasi keselarasan atau deviasi.\n"
        "- Akhiri dengan satu rekomendasi kebijakan atau program konkret yang dapat ditindaklanjuti.\n"
    ),
    "akademisi": (
        "- Arahkan analisis pada kerangka teori dan implikasi metodologis yang relevan.\n"
        "- Catat secara eksplisit keterbatasan data berita ini dibanding data primer jika relevan.\n"
        "- Akhiri dengan satu pertanyaan penelitian spesifik atau gap empiris untuk kajian lebih lanjut.\n"
    ),
}

# Alias backward-compat — beberapa modul lama mungkin masih mereferensikan _SYSTEM_PROMPT
_SYSTEM_PROMPT = _SYSTEM_PROMPT_BPS

# ── Internal helpers ───────────────────────────────────────────────────────────

def _build_client() -> tuple[OpenAI, str]:
    """Wrapper internal — pakai build_chat_client() dari llm_client."""
    return build_chat_client()


def build_gemini_client() -> OpenAI:
    """
    Public wrapper untuk dipakai endpoint streaming di app.py.
    Mengembalikan Gemini client via build_chat_client().
    Catatan: gunakan build_chat_client() untuk mendapatkan (client, model).
    """
    client, _model = build_chat_client()
    return client


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


def prepare_insight_articles(
    *,
    period_label: str,
    date_from: str | None,
    date_to: str | None,
    supabase_client=None,
    articles: list[dict] | None = None,
) -> dict:
    """
    Siapkan artikel per kategori (semantic + fallback keyword).
    Return:
      {
        "pdrb": [...],
        "kemiskinan": [...],
        "pengangguran": [...],
        "article_count": int,
      }
    """
    fallback_articles = articles or []
    semantic_results = {}

    use_semantic = (
        supabase_client is not None
        and date_from is not None
        and date_to is not None
    )

    if use_semantic:
        print(f"[AI Insights] Menjalankan semantic search untuk periode {period_label}...")
        try:
            semantic_results = semantic_search_multi(
                queries=_SEMANTIC_QUERIES,
                supabase_client=supabase_client,
                date_from=date_from,
                date_to=date_to,
                top_k=_MAX_ARTICLES_PER_CAT,
                min_similarity=0.1,
            )
        except Exception as exc:
            print(f"[AI Insights] Semantic search gagal: {exc} -> fallback ke keyword.")
            semantic_results = {}
    else:
        print("[AI Insights] Semantic search tidak tersedia - fallback ke keyword filter.")

    pdrb_articles = _select_articles_for_category("pdrb", semantic_results, fallback_articles)
    kemiskinan_articles = _select_articles_for_category("kemiskinan", semantic_results, fallback_articles)
    pengangguran_articles = _select_articles_for_category("pengangguran", semantic_results, fallback_articles)

    article_count = len(pdrb_articles) + len(kemiskinan_articles) + len(pengangguran_articles)

    print(
        "[AI Insights] Konteks streaming: "
        f"PDRB={len(pdrb_articles)}, "
        f"Kemiskinan={len(kemiskinan_articles)}, "
        f"Pengangguran={len(pengangguran_articles)}"
    )

    return {
        "pdrb": pdrb_articles,
        "kemiskinan": kemiskinan_articles,
        "pengangguran": pengangguran_articles,
        "article_count": article_count,
    }


def build_stream_category_context(
    category: str,
    period_label: str,
    category_articles: list[dict],
    actor: str = "bps",
) -> dict:
    """
    Bangun prompt + source map untuk streaming per kategori.
    source_map format list:
      [{"tag_id":"P01", "num":1, "title":"...", "url":"..."}, ...]
    actor: "bps" | "pemerintah" | "akademisi"
    """
    conf   = _CATEGORY_CONFIG[category]
    prefix = conf["prefix"]
    label  = conf["label"]

    articles_text, id_map = _format_articles_for_prompt(category_articles, prefix)

    source_map = []
    for idx, tag_id in enumerate(sorted(id_map.keys()), 1):
        info = id_map[tag_id]
        source_map.append({
            "tag_id": tag_id,
            "num": idx,
            "title": info.get("title", ""),
            "url": info.get("url", ""),
        })

    # Instruksi tambahan per aktor (diinjeksi setelah instruksi umum)
    extra_instructions = _ACTOR_EXTRA_INSTRUCTIONS.get(actor, "")
    extra_block = f"{extra_instructions}" if extra_instructions else ""

    prompt = f"""Periode analisis: {period_label}
Kategori fokus: {label}

Instruksi penulisan:
- Tulis insight 3-5 kalimat dalam markdown ringan.
- Gunakan Bahasa Indonesia formal.
- Jika data tidak cukup, nyatakan secara eksplisit tanpa memaksakan kesimpulan.
- Jangan menulis daftar sumber terpisah di akhir.
{extra_block}
Format sitasi (WAJIB dipatuhi):
- Setiap kalimat faktual WAJIB diakhiri satu atau lebih marker sitasi sebelum tanda baca akhir.
- Format marker: [{prefix}xx] — huruf awalan {prefix} + 2 digit angka. Contoh: [{prefix}01], [{prefix}12].
- Satu kode per kurung siku: [{prefix}01][{prefix}07] ← BENAR
- DILARANG menggabungkan kode dengan koma dalam satu kurung: [{prefix}01, {prefix}07] ← SALAH
- DILARANG menulis angka polos tanpa huruf awalan dan kurung: "15" atau "24" ← SALAH, harus [{prefix}15] [{prefix}24]
- DILARANG menulis "BERITA-xx" atau kode lain selain [{prefix}xx]

Konteks berita {label}:
{articles_text}
"""

    return {
        "prompt": prompt,
        "source_map": source_map,
        "id_map": id_map,
    }


def stream_category_tokens(
    *,
    client: OpenAI,
    model: str,
    user_prompt: str,
    system_prompt: str | None = None,
    temperature: float = 0.35,
    max_tokens: int = 420,
):
    """Yield token delta dari LLM chat streaming untuk satu kategori insight.

    system_prompt: gunakan salah satu dari _ACTOR_PROMPTS (default: _SYSTEM_PROMPT_BPS).
    """
    resolved_prompt = system_prompt if system_prompt is not None else _SYSTEM_PROMPT_BPS
    stream = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": resolved_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
        timeout=300,
    )
    for chunk in stream:
        try:
            delta = chunk.choices[0].delta.content or ""
        except Exception:
            delta = ""
        if delta:
            yield delta


def normalize_inline_markers(
    text: str,
    prefixes: str = "PKT",
    single_prefix: str | None = None,
) -> str:
    """Normalisasi marker sitasi agar konsisten [P01]/[K01]/[T01].

    Menangani kasus output LLM yang tidak konsisten:
      - Bracket berkoma : [P19, P22]       → [P19][P22]
      - Mixed bare num  : [P02, 3, P04]    → [P02][P03][P04]
      - Marker tergabung: P01K02            → [P01][K02]
      - Marker bare     : P01               → [P01]
      - Angka polos*    : "nasional 15."   → "nasional [P15]."
        (*hanya jika single_prefix tersedia dan angka 2-digit 10-30)
    """
    if not text:
        return ""

    cls             = f"[{prefixes}]"
    _default_prefix = (single_prefix or prefixes[0]).upper()

    # ── Step 1: Expand bracket berkoma ─────────────────────────────────────────
    # [P19, P22]       → [P19][P22]
    # [P02, 3, 4, P13] → [P02][P03][P04][P13]
    def _expand_comma_in_bracket(match: re.Match) -> str:
        inner  = match.group(1)
        tokens = [t.strip() for t in inner.split(",")]

        # Prefix default: ambil dari token pertama yang punya huruf awalan
        dp = _default_prefix
        for tok in tokens:
            m = re.match(rf"([{prefixes}])", tok, re.IGNORECASE)
            if m:
                dp = m.group(1).upper()
                break

        result = []
        for tok in tokens:
            tok = tok.strip()
            if not tok:
                continue
            m_full = re.fullmatch(rf"([{prefixes}])(\d{{1,2}})", tok, re.IGNORECASE)
            m_num  = re.fullmatch(r"(\d{1,2})", tok)
            if m_full:
                result.append(f"[{m_full.group(1).upper()}{int(m_full.group(2)):02d}]")
            elif m_num:
                result.append(f"[{dp}{int(m_num.group(1)):02d}]")

        return "".join(result) if result else match.group(0)

    comma_pat  = rf"\[([{prefixes}]\d{{1,2}}(?:\s*,\s*[{prefixes}]?\d{{1,2}})+)\]"
    normalized = re.sub(comma_pat, _expand_comma_in_bracket, text, flags=re.IGNORECASE)

    # ── Step 2: Expand marker tergabung: P01K02 → [P01][K02] ──────────────────
    def _expand_concat(match: re.Match) -> str:
        token = match.group(0).upper()
        parts = re.findall(rf"{cls}\d{{2}}", token)
        return "".join(f"[{p}]" for p in parts)

    normalized = re.sub(rf"(?:{cls}\d{{2}}){{2,}}", _expand_concat, normalized, flags=re.IGNORECASE)

    # ── Step 3: Bungkus marker bare: P01 → [P01] ──────────────────────────────
    normalized = re.sub(rf"(?<!\[)\b({cls}\d{{2}})\b(?!\])", r"[\1]", normalized, flags=re.IGNORECASE)

    # ── Step 4: Recovery angka polos 2-digit sebelum tanda baca ───────────────
    # Hanya aktif jika single_prefix tersedia (per-kategori, misal "P"/"K"/"T").
    # Contoh: "swasembada pangan nasional 15." → "swasembada pangan nasional [P15]."
    # Hanya angka 2-digit (10-30) — hindari false positive pada angka kecil 1-9
    # yang sering muncul sebagai tanggal, langkah, dll.
    if single_prefix:
        pfx = single_prefix.upper()

        def _recover_bare(match: re.Match) -> str:
            num   = int(match.group(1))
            punct = match.group(2)
            if 1 <= num <= 30:
                return f"[{pfx}{num:02d}]{punct}"
            return match.group(0)

        # (?<!\w) → tidak didahului huruf/digit (hindari "Rp10," atau "step10,")
        # (\d{2}) → tepat 2 digit
        # ([,.](?!\d)) → diikuti koma/titik yang BUKAN desimal (hindari "49,4")
        normalized = re.sub(r"(?<!\w)(\d{2})([,.](?!\d))", _recover_bare, normalized)

    return normalized


def extract_sources_from_markers(text: str, source_map: list[dict]) -> list[dict]:
    """Ambil sources yang benar-benar disitasi di teks berdasarkan marker [Pxx/Kxx/Txx]."""
    if not text or not source_map:
        return []

    map_by_tag = {str(s.get("tag_id", "")).upper(): s for s in source_map}
    ids = re.findall(r"\[([PKT]\d{2})\]", text.upper())

    results = []
    seen = set()
    for tid in ids:
        if tid in seen:
            continue
        src = map_by_tag.get(tid)
        if not src:
            continue
        results.append(src)
        seen.add(tid)
        if len(results) >= _MAX_SOURCES_SHOWN:
            break

    return results


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
    Analisis berita menggunakan Gemini dengan RAG (pgvector semantic search).

    Alur utama (jika date_from + date_to + supabase_client tersedia):
      1. Semantic search per kategori via pgvector → top-30 artikel paling relevan
      2. Format artikel → kirim ke Gemini dengan konteks yang sudah di-rank
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

    # ── Build prompt dan kirim ke LLM ─────────────────────────────────────────
    client, model               = build_chat_client()
    user_prompt, id_map         = _build_user_prompt(
        pdrb_articles, kemiskinan_articles, pengangguran_articles, period_label
    )

    print(f"[AI Insights] Mengirim konteks ke LLM ({model}) — {period_label}...")
    print(f"[AI Insights] ID map: {len(id_map)} artikel ditandai.")

    # Gemini mendukung response_format json_object via OpenAI-compatible endpoint.
    # Jika gagal (provider tidak mendukung), tangkap dan parse manual via _extract_json.
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.4,
            max_tokens=1000,
            response_format={"type": "json_object"},
            timeout=300,
        )
    except Exception as exc:
        # Beberapa provider tidak mendukung response_format — retry tanpa parameter ini
        print(f"[AI Insights] response_format tidak didukung ({exc}) — retry tanpa JSON mode.")
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.4,
            max_tokens=1000,
            timeout=300,
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
