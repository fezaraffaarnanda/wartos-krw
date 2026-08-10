"""
relevance.py — Classifier tahap-1 (gerbang) untuk sistem WARTOS.

Tujuan: menyaring berita SEBELUM masuk classifier mahal (KBLI/Aktivitas/PDRB).
Berita dinilai 0-100 berdasarkan rubrik 4 kriteria. Hanya berita dengan skor
>= RELEVANCE_THRESHOLD yang dianggap relevan secara ekonomi dan layak dianalisis.

Pakai LLM Gemini (OpenAI-compatible), model sama dengan classifier KBLI.
Keputusan akhir is_relevant ditentukan di Python dari skor — bukan dari LLM —
agar threshold konsisten dan bisa di-audit/di-tuning.
"""

import json
import re
import time

# ── Konfigurasi ──────────────────────────────────────────────────────────────

RELEVANCE_THRESHOLD = 50
PROMPT_VERSION      = "rel-v1"   # fallback jika DB tidak tersedia

# Cache prompt aktif dari DB, dua tingkat:
#   - pointer (version saja, query murah lewat partial index one_active_prompt):
#     dicek ulang tiap _POINTER_TTL detik.
#   - teks penuh: di-refetch hanya kalau pointer menunjukkan versi berubah,
#     atau _TEXT_TTL habis.
# Alasan dua tingkat: di deployment serverless multi-worker, satu worker yang
# meng-apply prompt baru hanya meng-invalidate cache-nya sendiri
# (invalidate_prompt_cache). Worker lain akan terus menandai baris dengan
# versi lama sampai TTL habis -- itu mencemari metrik per-versi-prompt, hal
# yang justru ingin diaudit oleh fitur ini. Pointer-poll murah menurunkan
# jendela divergensi itu dari _TEXT_TTL penuh menjadi _POINTER_TTL.
_TEXT_TTL    = 600  # detik
_POINTER_TTL = 15   # detik
_prompt_cache: dict = {
    "text": None,
    "version": None,
    "text_fetched_at": 0.0,
    "pointer_checked_at": 0.0,
}


# ── System prompt (rubrik) ───────────────────────────────────────────────────

SYSTEM_PROMPT = """Kamu adalah filter awal untuk berita ekonomi daerah Karawang. Tugasmu menilai apakah sebuah berita LAYAK dianalisis lebih lanjut untuk klasifikasi ekonomi (KBLI, aktivitas ekonomi, PDRB), atau harus dibuang karena tidak berbobot.

Konteks: Sistem ini membantu BPS memetakan aktivitas ekonomi dari pemberitaan lokal. Berita yang "berbobot" adalah yang mengandung sinyal ekonomi nyata — bukan seremoni, bukan politik murni, bukan kriminal, bukan human-interest.

Nilai berita berdasarkan 4 kriteria berikut (total 100 poin):

1. ANGKA EKONOMI KONKRET (0-30)
   Ada nilai investasi, omzet, jumlah tenaga kerja, volume produksi, nilai ekspor/impor, harga, atau target kuantitatif. Makin spesifik angkanya, makin tinggi skornya. Tanpa angka sama sekali → maksimal 10.

2. ENTITAS USAHA TERIDENTIFIKASI (0-25)
   Menyebut perusahaan, pabrik, kawasan industri, UMKM, koperasi, komoditas, atau sektor usaha spesifik. Bukan sekadar "pemerintah" atau "masyarakat". Seremoni tanpa entitas usaha nyata → rendah.

3. DAMPAK PRODUKSI/DISTRIBUSI/KONSUMSI (0-25)
   Berita menggambarkan aktivitas ekonomi riil: produksi naik/turun, pasar dibuka, distribusi terganggu, daya beli berubah, lapangan kerja. Bukan sekadar peresmian simbolis, kunjungan pejabat, atau wacana.

4. SKALA DAMPAK (0-20)
   Lokal kecil/individual → rendah. Berpengaruh ke satu sektor, banyak pelaku, atau skala kabupaten → tinggi.

PANDUAN KEPUTUSAN:
- score >= 50  → relevan (layak dianalisis lanjut)
- score < 50   → tidak relevan (dibuang)

Berita BORDERLINE (score 40-59) wajib diberi alasan jelas agar bisa direview manual.

Contoh TIDAK RELEVAN: berita kecelakaan, kegiatan keagamaan, lomba, pelantikan pejabat tanpa konteks ekonomi, imbauan umum, cuaca, kriminal.

Contoh RELEVAN: pabrik baru investasi Rp X, panen raya komoditas Y sekian ton, PHK di sektor Z, harga bahan pokok naik, ekspor produk lokal, pertumbuhan UMKM.

Balas HANYA dalam format JSON valid:
{
  "score": <integer 0-100>,
  "is_relevant": <true|false>,
  "reason": "<1-2 kalimat alasan, sebut kriteria mana yang terpenuhi/tidak>"
}"""


# ── Helper ────────────────────────────────────────────────────────────────────

def get_active_prompt(*, force: bool = False) -> tuple[str, str]:
    """
    Ambil (prompt_text, version) aktif dari DB dengan cache dua tingkat.
    Fallback ke konstanta SYSTEM_PROMPT / PROMPT_VERSION jika DB gagal/kosong.
    """
    now = time.time()
    cache = _prompt_cache

    if force or now - cache["pointer_checked_at"] >= _POINTER_TTL:
        try:
            from repositories.relevance_prompt import RelevancePromptRepository
            pointer = RelevancePromptRepository().get_active_pointer()
        except Exception as exc:
            print(f"[Relevance] Gagal cek pointer prompt aktif: {exc}")
            pointer = None
        cache["pointer_checked_at"] = now
        if pointer and pointer.get("version") and pointer["version"] != cache["version"]:
            cache["text"] = None  # versi berubah -> paksa refetch teks penuh di bawah

    if cache["text"] is None or now - cache["text_fetched_at"] >= _TEXT_TTL:
        try:
            from repositories.relevance_prompt import RelevancePromptRepository
            row = RelevancePromptRepository().get_active()
        except Exception as exc:
            print(f"[Relevance] Gagal ambil prompt aktif dari DB: {exc}")
            row = None

        if row and (row.get("prompt_text") or "").strip():
            cache.update({
                "text":            row["prompt_text"],
                "version":         row.get("version") or PROMPT_VERSION,
                "text_fetched_at": now,
            })
        else:
            cache.update({
                "text":            SYSTEM_PROMPT,
                "version":         PROMPT_VERSION,
                "text_fetched_at": now,
            })
    return cache["text"], cache["version"]


def invalidate_prompt_cache() -> None:
    """Paksa reload prompt dari DB pada panggilan berikutnya (dipakai setelah
    apply versi baru). Hanya instan untuk worker yang memanggilnya -- worker
    lain tetap mengandalkan pointer-poll di get_active_prompt()."""
    _prompt_cache.update({
        "text": None, "version": None, "text_fetched_at": 0.0, "pointer_checked_at": 0.0,
    })


def build_classifier_model(llm_model: str) -> str:
    """Gabung nama model + versi prompt aktif untuk audit. Mis. 'deepseek-.../rel-v2'."""
    base = (llm_model or "unknown").strip()
    _, version = get_active_prompt()
    return f"{base}/{version}"


def _parse_response(raw: str) -> dict | None:
    """Parse JSON dari respons LLM secara defensif. Return None jika gagal."""
    if not raw:
        return None
    text = raw.strip()

    # Buang fence ```json ... ``` jika ada
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()

    try:
        data = json.loads(text)
    except Exception:
        # Fallback: cari objek JSON pertama di dalam teks
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group())
        except Exception:
            return None

    if not isinstance(data, dict) or "score" not in data:
        return None
    return data


# ── Public API ────────────────────────────────────────────────────────────────

def classify_relevance(
    content:   str | None,
    title:     str | None,
    llm_client,
    llm_model: str,
    *,
    prompt_override: str | None = None,
) -> dict | None:
    """
    Nilai relevansi ekonomi sebuah berita.

    prompt_override: pakai teks prompt ini alih-alih prompt aktif dari cache/DB
    -- dipakai dry-run eval draft prompt SEBELUM diaktifkan (RelevancePromptService
    .evaluate_draft), supaya menilai draft tidak butuh mengaktifkannya dulu.
    Saat dipakai, prompt_version pada hasil selalu "draft".

    Return dict:
        {
          "score":            int 0-100,
          "is_relevant":      bool,    # ditentukan dari score >= RELEVANCE_THRESHOLD
          "reason":           str,
          "classifier_model": str,     # 'model/rel-v1'
          "prompt_version":   str,     # 'rel-v1' -- sama dengan sisi kanan classifier_model
        }
    Return None jika client tidak tersedia, input kosong, atau prediksi gagal.
    Pemanggil harus memperlakukan None sebagai "tidak terklasifikasi" (fallback aman).
    """
    if llm_client is None:
        return None

    content_clean = (content or "").strip()
    title_clean   = (title   or "").strip()

    if not content_clean and not title_clean:
        return None

    MAX_CONTENT = 1500
    MAX_TITLE   = 200
    text_parts: list[str] = []
    if title_clean:
        text_parts.append(f"Judul: {title_clean[:MAX_TITLE]}")
    if content_clean:
        text_parts.append(f"Konten:\n{content_clean[:MAX_CONTENT]}")
    user_text = "\n\n".join(text_parts)

    if prompt_override is not None:
        active_prompt, active_version = prompt_override, "draft"
    else:
        active_prompt, active_version = get_active_prompt()

    from clients.llm import log_usage, provider_from_model
    provider = provider_from_model(llm_model)
    t0 = time.perf_counter()

    try:
        resp = llm_client.chat.completions.create(
            model=llm_model,
            messages=[
                {"role": "system", "content": active_prompt},
                {"role": "user",   "content": user_text},
            ],
            temperature=0,
            max_tokens=500,
            response_format={"type": "json_object"},
        )
        log_usage(
            feature="relevance",
            provider=provider,
            model=llm_model,
            usage=getattr(resp, "usage", None),
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
        raw = (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        log_usage(
            feature="relevance",
            provider=provider,
            model=llm_model,
            latency_ms=(time.perf_counter() - t0) * 1000,
            success=False,
            error=str(exc),
        )
        print(f"[Relevance] Gagal prediksi LLM: {exc}")
        return None

    data = _parse_response(raw)
    if data is None:
        print(f"[Relevance] Respons LLM tidak bisa diparse: {raw!r}")
        return None

    try:
        score = int(round(float(data.get("score", 0))))
    except (TypeError, ValueError):
        print(f"[Relevance] Skor tidak valid: {data.get('score')!r}")
        return None

    score = max(0, min(100, score))
    reason = str(data.get("reason") or "").strip()[:500]
    is_relevant = score >= RELEVANCE_THRESHOLD

    title_log = title_clean[:60] if title_clean else "(tanpa judul)"
    print(f"[Relevance] '{title_log}' → score={score} relevan={is_relevant}")

    classifier_model = (
        f"{(llm_model or 'unknown').strip()}/draft"
        if prompt_override is not None
        else build_classifier_model(llm_model)
    )

    return {
        "score":            score,
        "is_relevant":      is_relevant,
        "reason":           reason,
        "classifier_model": classifier_model,
        "prompt_version":   active_version,
    }
