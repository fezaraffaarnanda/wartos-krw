"""
kbli_classifier_llm.py — Klasifikasi KBLI berbasis LLM (Gemini) + Embedding Similarity.

Arsitektur:
  1. Embed teks artikel menggunakan Gemini Embedding (1536-dim)
  2. Cari top-K kandidat KBLI via RPC match_kbli (pgvector cosine similarity)
  3. Tambahkan KE (Kemiskinan) dan PG (Pengangguran) sebagai opsi tetap
  4. Kirim kandidat + artikel ke Gemini dengan system prompt yang dioptimasi
  5. Parse dan validasi respons: harus berupa kode KBLI valid atau "Tidak Relevan"

Keunggulan vs model ML lama (SVC + TF-IDF):
  - Lebih akurat untuk konteks berita bahasa Indonesia
  - Tidak membutuhkan training ulang jika KBLI berubah
  - Kandidat RAG mengurangi hallusinasi LLM
  - Efisien: ~1500-2000 token per prediksi (Flash Lite = sangat hemat)
"""

import re
import time

from openai import OpenAI

from ai.base import KBLIClassifier
from ai.embeddings import generate_embedding

# ── Konstanta ──────────────────────────────────────────────────────────────────

# Panjang teks artikel yang dikirim ke LLM (hemat token, cukup untuk konteks)
_MAX_ARTICLE_CHARS = 600

# Panjang deskripsi KBLI yang disertakan per kandidat (cukup untuk konteks, tidak terlalu panjang)
_MAX_DESKRIPSI_CHARS = 200

# Kode yang valid sebagai output LLM (diupdate sinkron dengan KBLI_KEY_MAPPING di kbli.py)
_VALID_KBLI_CODES = frozenset({
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J",
    "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T",
    "U", "V", "KE", "PG",
})

# Kode khusus yang selalu disertakan di prompt (bukan dari similarity search)
_SPECIAL_CODES = {
    "KE": {
        "judul": "Kemiskinan",
        "deskripsi": (
            "Berita tentang tingkat kemiskinan penduduk, garis kemiskinan, warga miskin, "
            "kemiskinan ekstrem, bantuan sosial (bansos) berbasis kemiskinan, "
            "BPS data kemiskinan, program pengentasan kemiskinan."
        ),
    },
    "PG": {
        "judul": "Pengangguran",
        "deskripsi": (
            "Berita tentang angka pengangguran, Tingkat Pengangguran Terbuka (TPT), "
            "pencari kerja, ketenagakerjaan, Pemutusan Hubungan Kerja (PHK), "
            "lowongan kerja, penyerapan tenaga kerja, BPS data ketenagakerjaan."
        ),
    },
}

# System prompt template — dioptimasi untuk token efficiency + akurasi
_SYSTEM_PROMPT = """\
Kamu adalah sistem klasifikasi otomatis KBLI 2025 (Klasifikasi Baku Lapangan Usaha Indonesia) \
untuk berita ekonomi daerah.

TUGAS:
Baca berita yang diberikan, lalu pilih SATU kode KBLI yang paling sesuai dari DAFTAR KANDIDAT \
di bawah ini. Jika berita tidak membahas kegiatan ekonomi yang dapat diklasifikasikan ke KBLI, \
jawab "Tidak Relevan".

DAFTAR KANDIDAT KBLI:
{kandidat_block}

KATEGORI KHUSUS (selalu tersedia, bukan dari standar KBLI):
[KE] Kemiskinan — {ke_deskripsi}
[PG] Pengangguran — {pg_deskripsi}

ATURAN OUTPUT (WAJIB DIPATUHI):
1. Jawab HANYA dengan SATU kode (contoh: G atau KE atau Tidak Relevan)
2. Jangan tambahkan tanda baca, penjelasan, atau kata lain apa pun
3. Pilih kode yang merepresentasikan KEGIATAN EKONOMI UTAMA yang dibahas berita
4. Jika berita membahas kemiskinan → KE; pengangguran/ketenagakerjaan → PG
5. Jika topik tidak terkait kegiatan ekonomi → Tidak Relevan
6. Kode valid: {valid_codes}
"""

# User message template
_USER_PROMPT = """\
BERITA:
Judul: {judul}
Isi: {isi}

Kode KBLI:"""


# ── KBLIClassifierLLM ─────────────────────────────────────────────────────────

class KBLIClassifierLLM(KBLIClassifier):
    """
    Klasifikasi KBLI menggunakan pipeline: embedding similarity → Gemini LLM.

    Pemakaian:
        classifier = KBLIClassifierLLM(supabase, embed_client, llm_client, model_name)
        kode = classifier.classify("judul berita", "isi konten berita")
    """

    def __init__(
        self,
        supabase_client,
        embed_client: OpenAI,
        llm_client: OpenAI,
        llm_model: str,
        top_k: int = 5,
    ):
        """
        Args:
            supabase_client : instance supabase-py, untuk RPC match_kbli
            embed_client    : OpenAI client ke Gemini embedding endpoint
            llm_client      : OpenAI client ke Gemini chat endpoint
            llm_model       : nama model LLM (misal "gemini-3.1-flash-lite-preview")
            top_k           : jumlah kandidat KBLI dari similarity search (default 5)
        """
        self._supabase   = supabase_client
        self._embed      = embed_client
        self._llm        = llm_client
        self._model      = llm_model
        self._top_k      = top_k

    # ── Public method ─────────────────────────────────────────────────────────

    def classify(self, content: str | None, title: str | None = None) -> str | None:
        """
        Klasifikasi artikel ke kode KBLI.

        Args:
            content : isi konten berita (diutamakan)
            title   : judul berita (sebagai fallback jika content kosong, dan selalu disertakan)

        Return:
            str  : kode KBLI valid (misal "G", "KE", "Tidak Relevan") atau
            None : jika teks input kosong atau terjadi error fatal
        """
        # Gabungkan judul dan konten untuk embedding (lebih representatif)
        content_clean = (content or "").strip()
        title_clean   = (title   or "").strip()

        if not content_clean and not title_clean:
            return None

        prediction_text = content_clean or title_clean

        try:
            # 1. Cari top-K kandidat KBLI via similarity search
            candidates = self._fetch_candidates(prediction_text)

            # 2. Susun prompt dengan kandidat + artikel
            prompt = self._build_prompt(title_clean, content_clean, candidates)

            # 3. Panggil LLM
            raw_response = self._call_llm(prompt)

            # 4. Parse dan validasi respons
            return self._parse_response(raw_response)

        except Exception as exc:
            print(f"[KBLI LLM] Gagal klasifikasi: {exc}")
            return None

    # ── Private helpers ───────────────────────────────────────────────────────

    def _fetch_candidates(self, text: str) -> list[dict]:
        """
        Embed teks artikel lalu cari top-K KBLI mirip via RPC match_kbli.
        Return list of dicts: {kode, judul, deskripsi, similarity}
        KE dan PG tidak termasuk di sini — disertakan manual di prompt.
        """
        embedding = generate_embedding(text, client=self._embed)
        if embedding is None:
            print("[KBLI LLM] Gagal generate embedding — kandidat kosong, hanya KE/PG tersedia.")
            return []

        try:
            result = self._supabase.rpc(
                "match_kbli",
                {"query_embedding": embedding, "top_k": self._top_k},
            ).execute()
            return result.data or []
        except Exception as exc:
            print(f"[KBLI LLM] Gagal RPC match_kbli: {exc}")
            return []

    def _build_prompt(
        self,
        title: str,
        content: str,
        candidates: list[dict],
    ) -> str:
        """Susun user message dengan kandungan berita dan daftar kandidat KBLI."""
        # Format blok kandidat dari similarity search
        kandidat_lines = []
        for c in candidates:
            kode   = c.get("kode",      "?")
            judul  = c.get("judul",     "")
            deskr  = (c.get("deskripsi") or "")[:_MAX_DESKRIPSI_CHARS]
            kandidat_lines.append(f"[{kode}] {judul} — {deskr}")

        if kandidat_lines:
            kandidat_block = "\n".join(kandidat_lines)
        else:
            kandidat_block = "(Tidak ada kandidat dari pencarian semantik)"

        # Format valid codes string
        valid_codes_str = ", ".join(sorted(_VALID_KBLI_CODES)) + ", Tidak Relevan"

        # Format system prompt
        system = _SYSTEM_PROMPT.format(
            kandidat_block = kandidat_block,
            ke_deskripsi   = _SPECIAL_CODES["KE"]["deskripsi"],
            pg_deskripsi   = _SPECIAL_CODES["PG"]["deskripsi"],
            valid_codes    = valid_codes_str,
        )

        # Format teks artikel (potong agar hemat token)
        isi = content[:_MAX_ARTICLE_CHARS] if content else title
        if content and len(content) > _MAX_ARTICLE_CHARS:
            isi += "..."

        user_msg = _USER_PROMPT.format(
            judul = title or "(tanpa judul)",
            isi   = isi   or "(tanpa konten)",
        )

        return system + "\n" + user_msg

    def _call_llm(self, prompt: str) -> str:
        """
        Kirim prompt ke Gemini dan return teks respons raw.
        Retry 1x jika terjadi transient error.
        """
        messages = [{"role": "user", "content": prompt}]

        for attempt in range(2):
            try:
                response = self._llm.chat.completions.create(
                    model       = self._model,
                    messages    = messages,
                    max_tokens  = 20,      # output hanya 1 kode, maks ~5 token
                    temperature = 0.0,     # deterministik — tidak ada kreativitas
                )
                content = response.choices[0].message.content
                return (content or "").strip()
            except Exception as exc:
                if attempt == 0:
                    print(f"[KBLI LLM] Error LLM (attempt {attempt+1}): {exc} — retry...")
                    time.sleep(1)
                else:
                    raise

        return ""

    def _parse_response(self, raw: str) -> str | None:
        """
        Bersihkan dan validasi respons LLM.

        Strategi:
        - Ambil token pertama (sebelum spasi/newline)
        - Uppercase dan strip tanda baca
        - Cek apakah ada di _VALID_KBLI_CODES
        - Handle "Tidak Relevan" sebagai case insensitive
        - Fallback: return None jika tidak dikenali
        """
        if not raw:
            return None

        # Ambil token pertama — LLM seharusnya hanya mengeluarkan satu kata
        token = raw.split()[0] if raw.split() else raw

        # Bersihkan karakter non-alfanumerik di tepi (titik, koma, tanda kutip, dll.)
        token = re.sub(r"^[^A-Za-z0-9]+|[^A-Za-z0-9]+$", "", token)

        # Cek "Tidak Relevan" secara lengkap (case insensitive)
        if "tidak relevan" in raw.lower():
            return "Tidak Relevan"

        # Normalisasi: uppercase
        token_upper = token.upper()

        if token_upper in _VALID_KBLI_CODES:
            return token_upper

        # Fallback untuk format tak terduga: scan seluruh respons cari kode valid
        for code in _VALID_KBLI_CODES:
            pattern = r"\b" + re.escape(code) + r"\b"
            if re.search(pattern, raw, re.IGNORECASE):
                return code

        print(f"[KBLI LLM] Respons tidak dikenali: '{raw}' — return None")
        return None
