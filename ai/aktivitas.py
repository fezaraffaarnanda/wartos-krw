"""
aktivitas_utils.py — Klasifikasi Aktivitas Ekonomi untuk pemantauan PDRB BPS.

27 kategori aktivitas ekonomi sesuai master BPS Kabupaten Karawang.
Klasifikasi menggunakan LLM Gemini (pure LLM, tanpa embedding).
Format output: "9/Aktivitas industri makanan dan minuman selain CPO"
"""

import re
import time

# ── Label Aktivitas Ekonomi ──────────────────────────────────────────────────

AKTIVITAS_LABELS: dict[int, str] = {
    1:  "Kondisi perekonomian di kabupaten/kota secara umum",
    2:  "Aktivitas panen hasil tanaman pangan (padi, jagung, palawija)",
    3:  "Aktivitas panen hasil tanaman lainnya (perkebunan, hortikultura)",
    4:  "Aktivitas rumah potong hewan (RPH)",
    5:  "Aktivitas penangkapan/budidaya ikan laut dan darat",
    6:  "Aktivitas pertambangan non migas (batubara, bijih logam, dll)",
    7:  "Aktivitas penggalian (pasir, kerikil)",
    8:  "Aktivitas produksi CPO",
    9:  "Aktivitas industri makanan dan minuman selain CPO",
    10: "Aktivitas penjualan/penyaluran migas (BBM & LPG)",
    11: "Aktivitas penjualan dan reparasi mobil dan sepeda motor",
    12: "Aktivitas pengiriman barang/ekspedisi",
    13: "Aktivitas/keramaian di terminal bis/travel/pool",
    14: "Aktivitas usaha perhotelan",
    15: "Jumlah pengunjung rumah sakit, klinik, dan laboratorium kesehatan",
    16: "Aktivitas/transaksi jual beli di pasar tradisional",
    17: "Aktivitas/transaksi jual beli di mall/pusat perbelanjaan modern terbesar",
    18: "Banyaknya penyewaan ruang untuk berjualan di mall/supermarket (tenant)",
    19: "Aktivitas/keramaian pengunjung restoran dan rumah makan",
    20: "Jumlah pengunjung tempat wisata komersial",
    21: "Aktivitas penyaluran dana bantuan penanggulangan bencana oleh LNPRT",
    22: "Aktivitas partai politik (kampanye, kongres, musda, dll)",
    23: "Aktivitas perayaan kegiatan keagamaan",
    24: "Aktivitas pembangunan/renovasi besar-besaran rumah/tempat tinggal",
    25: "Aktivitas pembangunan gedung dan infrastruktur (jalan, jembatan, dll)",
    26: "Aktivitas pemberian bansos dari pemerintah",
    27: "Aktivitas bongkar muat di pelabuhan/bandara/stasiun",
}

# ── Regex untuk strip caption foto ───────────────────────────────────────────
# Pola: baris yang diakhiri dengan "-Nama/Sumber-" atau "-Nama/Sumber Grup-"
# Contoh: "-Yeri Noveli/Radar Tegal Grup-" atau "-Foto: Kompas-"
_RE_CAPTION_LINE = re.compile(
    r"^.{0,200}"           # teks pendahulu caption (max 200 char)
    r"-\s*[^-\n]{3,60}"    # "-Nama"
    r"\/[^-\n]{2,40}"      # "/Sumber"
    r"(?:\s+\w+)*\s*-\s*$",# " Grup-" opsional + akhir baris
    re.MULTILINE,
)
# Pola sederhana: baris pendek yang hanya berisi kredit fotografer
_RE_CREDIT_LINE = re.compile(
    r"^\s*-?[A-Z][a-zA-Z .]{3,50}\/[A-Za-z .]{3,40}(?:\s+\w+)*\s*-?\s*$",
    re.MULTILINE,
)


def _clean_content_for_llm(content: str) -> str:
    """Bersihkan konten berita dari caption foto dan kredit fotografer
    sebelum dikirim ke LLM, agar tidak mengganggu klasifikasi."""
    lines = content.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # Skip baris yang terlihat seperti caption foto
        if _RE_CAPTION_LINE.match(line) or _RE_CREDIT_LINE.match(line):
            continue
        # Skip baris yang dimulai dengan kata besar + " - " + teks pendek
        # (pola judul caption: "JALAN HILANG - Sekretaris ...")
        # yang SAMA PERSIS dengan kalimat pertama artikel (duplikasi foto)
        if stripped and stripped.isupper() and len(stripped) < 50:
            continue
        cleaned.append(stripped)
    # Hapus baris kosong berlebihan
    result = "\n".join(l for l in cleaned if l)
    return result


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """Kamu adalah klasifikator aktivitas ekonomi untuk sistem pemantauan PDRB BPS.

Tugasmu: tentukan SATU kategori aktivitas ekonomi yang paling relevan dengan isi berita.

DAFTAR KATEGORI (jawab HANYA dengan angkanya):
 1. Kondisi perekonomian di kabupaten/kota secara umum
 2. Aktivitas panen hasil tanaman pangan (padi, jagung, palawija)
 3. Aktivitas panen hasil tanaman lainnya (perkebunan, hortikultura)
 4. Aktivitas rumah potong hewan (RPH)
 5. Aktivitas penangkapan/budidaya ikan laut dan darat
 6. Aktivitas pertambangan non migas (batubara, bijih logam, dll)
 7. Aktivitas penggalian (pasir, kerikil)
 8. Aktivitas produksi CPO
 9. Aktivitas industri makanan dan minuman selain CPO
10. Aktivitas penjualan/penyaluran migas (BBM & LPG)
11. Aktivitas penjualan dan reparasi mobil dan sepeda motor
12. Aktivitas pengiriman barang/ekspedisi
13. Aktivitas/keramaian di terminal bis/travel/pool
14. Aktivitas usaha perhotelan
15. Jumlah pengunjung rumah sakit, klinik, dan laboratorium kesehatan
16. Aktivitas/transaksi jual beli di pasar tradisional
17. Aktivitas/transaksi jual beli di mall/pusat perbelanjaan modern terbesar
18. Banyaknya penyewaan ruang untuk berjualan di mall/supermarket (tenant)
19. Aktivitas/keramaian pengunjung restoran dan rumah makan
20. Jumlah pengunjung tempat wisata komersial
21. Aktivitas penyaluran dana bantuan penanggulangan bencana oleh LNPRT
22. Aktivitas partai politik (kampanye, kongres, musda, dll)
23. Aktivitas perayaan kegiatan keagamaan
24. Aktivitas pembangunan/renovasi besar-besaran rumah/tempat tinggal
25. Aktivitas pembangunan gedung dan infrastruktur (jalan, jembatan, dll)
26. Aktivitas pemberian bansos dari pemerintah
27. Aktivitas bongkar muat di pelabuhan/bandara/stasiun

═══════════════════════════════════════════════════════════
SINYAL KUAT — jika menemukan kata kunci berikut, langsung pilih kategorinya:

▸ Kat 25 (INFRASTRUKTUR): ruas jalan, jalan kabupaten, jalan desa, jalan rusak,
  jembatan, SK jalan, inventarisasi jalan, aset jalan, DPUPR, Dinas PU,
  perbaikan jalan, pembangunan gedung, kantor pemerintah, sekolah baru,
  irigasi, drainase, embung, trotoar, talud, gorong-gorong.
  → PILIH 25 meskipun artikel menyebut APBD, pemerintah, atau anggaran.

▸ Kat 24 (PERUMAHAN): bedah rumah, RTLH, rumah tidak layak huni, KPR,
  perumahan rakyat, subsidi rumah, renovasi rumah warga, rehab rumah.
  → Khusus TEMPAT TINGGAL. Gedung pemerintah/sekolah → tetap kat 25.

▸ Kat 2  (TANAMAN PANGAN): padi, gabah, jagung, kedelai, singkong, ketela,
  palawija, ubi, panen padi, tanam padi, produksi beras.
  → BUKAN infrastruktur, BUKAN perdagangan beras di pasar → kat 16.

▸ Kat 3  (TANAMAN LAIN): kelapa sawit (bukan CPO), karet, cabai, bawang,
  buah-buahan, tembakau, tebu, perkebunan, hortikultura.

▸ Kat 8  (CPO): minyak sawit mentah, crude palm oil, pabrik CPO, PKS.

▸ Kat 10 (MIGAS): BBM, bensin, solar, LPG, Pertamina, SPBU, harga BBM.

▸ Kat 16 (PASAR TRADISIONAL): pasar tradisional, pasar rakyat, PKL,
  pedagang kaki lima, pasar desa, los pasar, kios pasar.

▸ Kat 17 (MODERN): mall, supermarket, hypermarket, minimarket, Indomaret,
  Alfamart, Giant, Transmart, pusat perbelanjaan modern.

▸ Kat 21 (BENCANA/LNPRT): PMI, relawan, LSM, LNPRT, donasi bencana,
  bantuan korban banjir/gempa/longsor dari organisasi non-pemerintah.

▸ Kat 26 (BANSOS): PKH, BPNT, BLT, BLT-DD, KIS, KIP, Jamkesda, bansos
  dari pemerintah, Dinas Sosial, subsidi pemerintah reguler.
  → Bukan dari LSM/relawan (itu kat 21).

▸ Kat 22 (POLITIK): pilkada, pilbup, kampanye, calon bupati, calon wali kota,
  partai politik, DPC, DPD, kongres partai, musda.

═══════════════════════════════════════════════════════════
ATURAN PENTING:

• Kat 1 HANYA untuk berita yang membahas kondisi ekonomi MAKRO dan AGREGAT
  (PDRB, pertumbuhan ekonomi daerah, inflasi, deflasi, NTP, IHK, neraca
  perdagangan). BUKAN untuk berita tentang program tertentu atau sektor spesifik.
  Jika ada kata APBD tapi fokusnya adalah jalan/infrastruktur → pilih 25.

• Kat 2 TIDAK ADA hubungannya dengan infrastruktur, jalan, atau bangunan.
  Jika ragu antara 2 dan 25 → lihat apakah ada kata "padi/jagung/panen" → 2,
  atau ada kata "jalan/jembatan/gedung" → 25.

• Jika tidak cocok dengan satu pun kategori di atas → jawab 0.

Jawab HANYA dengan SATU angka (0–27). Tidak perlu penjelasan."""


def format_aktivitas_hasil(nomor: int) -> str | None:
    """Format nomor aktivitas ke bentuk yang disimpan di DB.

    Contoh output: "9/Aktivitas industri makanan dan minuman selain CPO"
    Return "—" untuk nomor 0 (tidak relevan).
    Return None jika nomor di luar range.
    """
    if nomor == 0:
        return "—"
    label = AKTIVITAS_LABELS.get(nomor)
    if label:
        return f"{nomor}/{label}"
    return None


def predict_aktivitas_label(
    content:   str | None,
    title:     str | None,
    llm_client,
    llm_model: str,
) -> str | None:
    """
    Prediksi label Aktivitas Ekonomi untuk sebuah berita.

    Args:
        content    : isi konten berita
        title      : judul berita
        llm_client : OpenAI-compatible client (Gemini)
        llm_model  : nama model LLM

    Return:
        str  : contoh "9/Aktivitas industri makanan dan minuman selain CPO" atau "—"
        None : jika client tidak tersedia, input kosong, atau prediksi gagal
    """
    if llm_client is None:
        return None

    content_raw   = (content or "").strip()
    title_clean   = (title   or "").strip()

    if not content_raw and not title_clean:
        return None

    # Bersihkan konten dari caption foto sebelum dikirim ke LLM
    content_clean = _clean_content_for_llm(content_raw) if content_raw else ""

    # Batasi panjang: title maks 200 char, konten maks 1200 char
    MAX_CONTENT = 1200
    MAX_TITLE   = 200
    text_parts  = []
    if title_clean:
        text_parts.append(f"Judul: {title_clean[:MAX_TITLE]}")
    if content_clean:
        text_parts.append(f"Konten:\n{content_clean[:MAX_CONTENT]}")
    user_text = "\n\n".join(text_parts)

    from clients.llm import log_usage, provider_from_model
    provider = provider_from_model(llm_model)
    t0 = time.perf_counter()

    try:
        resp = llm_client.chat.completions.create(
            model=llm_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_text},
            ],
            temperature=0,
            max_tokens=10,
        )
        log_usage(
            feature="aktivitas",
            provider=provider,
            model=llm_model,
            usage=getattr(resp, "usage", None),
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
        raw = (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        log_usage(
            feature="aktivitas",
            provider=provider,
            model=llm_model,
            latency_ms=(time.perf_counter() - t0) * 1000,
            success=False,
            error=str(exc),
        )
        print(f"[Aktivitas] Gagal prediksi LLM: {exc}")
        return None

    # Parse: ambil angka pertama dari respons
    m = re.search(r"\d+", raw)
    if not m:
        print(f"[Aktivitas] Respons LLM tidak mengandung angka: {raw!r}")
        return None

    nomor = int(m.group())
    result = format_aktivitas_hasil(nomor)
    if result is None:
        print(f"[Aktivitas] Nomor di luar range (0-27): {nomor} — raw={raw!r}")
        return None

    title_log = title_clean[:60] if title_clean else "(tanpa judul)"
    print(f"[Aktivitas] '{title_log}' → {nomor} ({result})")
    return result

