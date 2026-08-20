"""
kbli_utils.py — Utilitas integrasi klasifikasi KBLI untuk app dan script backfill.

Mapping kode KBLI sesuai KBLI 2025 (22 kategori A–V) + 2 kategori custom:
  - KE : Kemiskinan
  - PG : Pengangguran

Klasifikasi menggunakan LLM Gemini + pgvector similarity search (KBLIClassifierLLM).
"""

from ai.base import KBLIClassifier

# ── KBLI 2025 Mapping kode → judul ──────────────────────────────────────────
# Sinkron dengan KBLI_KEY_MAPPING di static/js/script.js
# 22 kategori standar (A–V) + 2 kategori custom (KE, PG)

KBLI_KEY_MAPPING = {
    "A":   "Pertanian, Kehutanan, dan Perikanan",
    "B":   "Pertambangan dan Penggalian",
    "C":   "Industri",
    "D":   "Penyediaan Listrik, Gas, Uap/Air Panas, dan Udara Dingin",
    "E":   "Penyediaan Air; Pengelolaan Air Limbah, Penanganan Limbah, dan Remediasi",
    "F":   "Konstruksi",
    "G":   "Perdagangan Besar dan Eceran",
    "H":   "Transportasi dan Penyimpanan",
    "I":   "Aktivitas Penyediaan Akomodasi dan Makan Minum",
    "J":   "Aktivitas Penerbitan, Penyiaran, serta Produksi dan Distribusi Konten",
    "K":   "Aktivitas Telekomunikasi, Pemrograman Komputer, Konsultansi, dan Jasa Informasi",
    "L":   "Aktivitas Keuangan dan Asuransi",
    "M":   "Aktivitas Real Estat",
    "N":   "Aktivitas Profesional, Ilmiah, dan Teknis",
    "O":   "Aktivitas Administratif dan Penunjang Usaha",
    "P":   "Administrasi Pemerintahan dan Pertahanan, Serta Jaminan Sosial Wajib",
    "Q":   "Pendidikan",
    "R":   "Aktivitas Kesehatan Manusia dan Aktivitas Sosial",
    "S":   "Kesenian, Olahraga, dan Rekreasi",
    "T":   "Aktivitas Jasa Lainnya",
    "U":   "Aktivitas Rumah Tangga sebagai Pemberi Kerja",
    "V":   "Aktivitas Badan Internasional dan Badan Ekstra Internasional Lainnya",

    # custom
    "KE":  "Kemiskinan",
    "PG":  "Pengangguran",
}


def format_kbli_hasil(kode: str | None) -> str | None:
    """Format kode KBLI ke bentuk yang ditampilkan di tabel dashboard.

    Contoh output:
        "G/Perdagangan Besar dan Eceran"
        "KE/Kemiskinan"
        "Tidak Relevan"
        None   (jika kode kosong)
    """
    if not kode:
        return None

    normalized = str(kode).strip()
    if not normalized:
        return None

    # "Tidak Relevan" dan "—" dikembalikan apa adanya
    if normalized in ("Tidak Relevan", "—"):
        return normalized

    normalized_upper = normalized.upper()
    deskripsi = KBLI_KEY_MAPPING.get(normalized_upper)
    if deskripsi:
        return f"{normalized_upper}/{deskripsi}"

    # Kode tidak dikenali — kembalikan apa adanya (misal data lama)
    return normalized


def load_kbli_llm_classifier(
    supabase_client,
    embed_client,
    llm_client,
    llm_model: str,
) -> KBLIClassifier | None:
    """
    Buat instance KBLIClassifierLLM.
    Return instance classifier, atau None jika gagal inisialisasi.

    Args:
        supabase_client : instance supabase-py, untuk RPC match_kbli
        embed_client    : OpenAI client ke Gemini embedding endpoint
        llm_client      : OpenAI client ke Gemini chat endpoint
        llm_model       : nama model LLM

    Pemakaian di app.py:
        _kbli_classifier = load_kbli_llm_classifier(supabase, embed_client, llm_client, model)
    """
    try:
        from ai.kbli_classifier import KBLIClassifierLLM
    except Exception as exc:
        print(f"[KBLI] Gagal import KBLIClassifierLLM: {exc}")
        return None

    if supabase_client is None:
        print("[KBLI] Supabase client tidak tersedia — LLM classifier tidak diinisialisasi.")
        return None
    if embed_client is None:
        print("[KBLI] Embedding client tidak tersedia — LLM classifier tidak diinisialisasi.")
        return None
    if llm_client is None:
        print("[KBLI] LLM client tidak tersedia — LLM classifier tidak diinisialisasi.")
        return None

    try:
        classifier = KBLIClassifierLLM(
            supabase_client = supabase_client,
            embed_client    = embed_client,
            llm_client      = llm_client,
            llm_model       = llm_model,
            top_k           = 5,
        )
        print(f"[KBLI] LLM Classifier aktif (model: {llm_model}).")
        return classifier
    except Exception as exc:
        print(f"[KBLI] Gagal inisialisasi KBLIClassifierLLM: {exc}")
        return None


def predict_kbli_label(
    content: str | None,
    classifier: KBLIClassifier | None,
    title:  str | None = None,
) -> str | None:
    """
    Prediksi label KBLI untuk konten berita dan format hasilnya.

    Args:
        content    : isi konten berita (diutamakan)
        classifier : instance KBLIClassifierLLM (atau None jika tidak tersedia)
        title      : judul berita (opsional, digunakan sebagai konteks tambahan)

    Return:
        str  : label terformat, contoh "G/Perdagangan Besar dan Eceran" atau "Tidak Relevan"
        None : jika classifier tidak tersedia atau input kosong
    """
    if classifier is None:
        return None

    if not content and not title:
        return None

    content_clean = (content or "").strip()
    title_clean   = (title   or "").strip()

    if not content_clean and not title_clean:
        return None

    try:
        kode = classifier.classify(content_clean, title=title_clean)
    except Exception as exc:
        print(f"[KBLI] Gagal prediksi: {exc}")
        return None

    if not kode:
        return None

    return format_kbli_hasil(kode)
