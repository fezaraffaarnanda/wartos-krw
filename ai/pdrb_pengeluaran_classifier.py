"""
Klasifikasi PDRB pengeluaran berbasis embedding similarity + Gemini.

Pipeline:
1. Embed artikel
2. Ambil kandidat terdekat dari pdrb_pengeluaran_master via pgvector
3. Minta Gemini memilih SATU leaf-level code paling relevan
4. Parse dan validasi output
"""

import re
import time

from openai import OpenAI

from ai.embeddings import generate_embedding
from ai.pdrb_pengeluaran import (
    PDRB_PENGELUARAN_LABELS,
    PDRB_PENGELUARAN_PARENT_LABELS,
)

_MAX_ARTICLE_CHARS = 800
_MAX_DESKRIPSI_CHARS = 240
_VALID_CODES = frozenset(PDRB_PENGELUARAN_LABELS)

_SYSTEM_PROMPT = """\
Kamu adalah sistem klasifikasi PDRB pengeluaran untuk berita ekonomi daerah.

TUGAS:
Pilih SATU kode leaf-level PDRB pengeluaran yang paling sesuai dengan isi berita.
Jika berita tidak cukup jelas merepresentasikan komponen pengeluaran, jawab "Tidak Relevan".

KELUARGA KATEGORI:
- PKRT  = Pengeluaran Konsumsi Rumah Tangga
- PKP   = Pengeluaran Konsumsi Pemerintah
- PMTB  = Pembentukan Modal Tetap Bruto (investasi/aset tetap)
- PKLNPRT = Pengeluaran Konsumsi LNPRT/non-profit
- PI    = Perubahan Inventori/stok barang

PRINSIP PEMILIHAN:
1. Pilih kode paling spesifik di level komponen/divisi, bukan sekadar keluarga besarnya.
2. Bedakan pelaku pengeluaran dengan tegas: rumah tangga vs pemerintah vs LNPRT.
3. PMTB dipakai untuk belanja modal/aset tetap/investasi jangka panjang.
4. PI dipakai untuk perubahan stok, persediaan, work in progress, atau penumpukan barang.
5. Jika berita tidak cukup kuat mengarah ke salah satu komponen, jawab "Tidak Relevan".

DAFTAR KANDIDAT:
{kandidat_block}

ATURAN OUTPUT:
1. Jawab HANYA dengan satu kode valid atau tepat "Tidak Relevan"
2. Jangan menambahkan penjelasan, tanda baca, atau kata lain
3. Kode valid: {valid_codes}
"""

_USER_PROMPT = """\
BERITA:
Judul: {judul}
Isi: {isi}

Kode PDRB Pengeluaran:"""


class PDRBPengeluaranClassifierLLM:
    def __init__(
        self,
        supabase_client,
        embed_client: OpenAI,
        llm_client: OpenAI,
        llm_model: str,
        top_k: int = 7,
    ):
        self._supabase = supabase_client
        self._embed = embed_client
        self._llm = llm_client
        self._model = llm_model
        self._top_k = top_k

    def classify(self, content: str | None, title: str | None = None) -> str | None:
        content_clean = (content or "").strip()
        title_clean = (title or "").strip()
        if not content_clean and not title_clean:
            return None

        prediction_text = content_clean or title_clean

        try:
            embedding = generate_embedding(prediction_text, client=self._embed)
            if embedding is None:
                print("[PDRB Pengeluaran] Gagal generate embedding artikel.")
                return None

            return self.classify_with_embedding(content_clean, title_clean, embedding)
        except Exception as exc:
            print(f"[PDRB Pengeluaran] Gagal klasifikasi: {exc}")
            return None

    def classify_with_embedding(
        self,
        content: str | None,
        title: str | None,
        embedding: list[float],
    ) -> str | None:
        content_clean = (content or "").strip()
        title_clean = (title or "").strip()
        candidates = self._fetch_candidates_from_embedding(embedding)
        prompt = self._build_prompt(title_clean, content_clean, candidates)
        raw_response = self._call_llm(prompt)
        return self._parse_response(raw_response)

    def _fetch_candidates_from_embedding(self, embedding: list[float]) -> list[dict]:
        try:
            result = self._supabase.rpc(
                "match_pdrb_pengeluaran",
                {"query_embedding": embedding, "top_k": self._top_k},
            ).execute()
            return result.data or []
        except Exception as exc:
            print(f"[PDRB Pengeluaran] Gagal RPC match_pdrb_pengeluaran: {exc}")
            return []

    def _build_prompt(self, title: str, content: str, candidates: list[dict]) -> str:
        kandidat_lines = []
        for candidate in candidates:
            kode = str(candidate.get("kode") or "?").strip().upper()
            parent_code = str(candidate.get("parent_code") or "").strip().upper()
            parent_judul = str(candidate.get("parent_judul") or "").strip()
            judul = str(candidate.get("judul") or "").strip()
            deskripsi = str(candidate.get("deskripsi") or "").strip()[:_MAX_DESKRIPSI_CHARS]
            family = parent_judul or PDRB_PENGELUARAN_PARENT_LABELS.get(parent_code, parent_code)
            kandidat_lines.append(
                f"[{kode}] {parent_code} - {family} - {judul} - {deskripsi}"
            )

        kandidat_block = "\n".join(kandidat_lines) if kandidat_lines else "(Tidak ada kandidat)"
        valid_codes = ", ".join(sorted(_VALID_CODES)) + ", Tidak Relevan"

        system = _SYSTEM_PROMPT.format(
            kandidat_block=kandidat_block,
            valid_codes=valid_codes,
        )

        isi = content[:_MAX_ARTICLE_CHARS] if content else title
        if content and len(content) > _MAX_ARTICLE_CHARS:
            isi += "..."

        user_msg = _USER_PROMPT.format(
            judul=title or "(tanpa judul)",
            isi=isi or "(tanpa konten)",
        )
        return system + "\n" + user_msg

    def _call_llm(self, prompt: str) -> str:
        messages = [{"role": "user", "content": prompt}]

        for attempt in range(2):
            try:
                response = self._llm.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    max_tokens=20,
                    temperature=0.0,
                )
                content = response.choices[0].message.content
                return (content or "").strip()
            except Exception as exc:
                if attempt == 0:
                    print(f"[PDRB Pengeluaran] Error LLM (attempt {attempt + 1}): {exc} - retry...")
                    time.sleep(1)
                else:
                    raise

        return ""

    def _parse_response(self, raw: str) -> str | None:
        if not raw:
            return None

        if "tidak relevan" in raw.lower():
            return "Tidak Relevan"

        token = raw.split()[0] if raw.split() else raw
        token = re.sub(r"^[^A-Za-z0-9-]+|[^A-Za-z0-9-]+$", "", token)
        token_upper = token.upper()
        if token_upper in _VALID_CODES:
            return token_upper

        for code in _VALID_CODES:
            pattern = r"\b" + re.escape(code) + r"\b"
            if re.search(pattern, raw, re.IGNORECASE):
                return code

        print(f"[PDRB Pengeluaran] Respons tidak dikenali: '{raw}'")
        return None
