"""
Utilitas klasifikasi PDRB pengeluaran untuk berita ekonomi.

Level klasifikasi yang dipakai adalah level leaf/divisi-komponen, bukan hanya
5 kelompok utama. Format nilai yang disimpan di DB:

    KODE/Label

Contoh:
    PKRT-01/Makanan dan minuman tidak beralkohol
    PMTB-01/Bangunan dan Tempat Tinggal
    Tidak Relevan
    --
"""

from typing import Any, Protocol


PDRB_PENGELUARAN_PARENT_LABELS = {
    "PKRT": "Pengeluaran Konsumsi Rumah Tangga",
    "PKP": "Pengeluaran Konsumsi Pemerintah",
    "PMTB": "Pembentukan Modal Tetap Bruto",
    "PKLNPRT": "Pengeluaran Konsumsi LNPRT",
    "PI": "Perubahan Inventori",
}

PDRB_PENGELUARAN_REFERENCE_SPECS = (
    {
        "parent_code": "PKRT",
        "file_name": " Pengeluaran Konsumsi Rumah Tangga.xlsx",
        "has_division": True,
    },
    {
        "parent_code": "PKP",
        "file_name": "Klasifikasi Pengeluaran Konsumsi Pemerintah.xlsx",
        "has_division": True,
    },
    {
        "parent_code": "PMTB",
        "file_name": "Pembentukan Modal Tetap Bruto (PMTB).xlsx",
        "has_division": False,
    },
    {
        "parent_code": "PKLNPRT",
        "file_name": "Pengeluaran Konsumsi Lembaga Non-Profit yang Melayani Rumah Tangga (PK-LNPRT).xlsx",
        "has_division": True,
    },
    {
        "parent_code": "PI",
        "file_name": "Perubahan Inventori (Stok Barang).xlsx",
        "has_division": False,
    },
)

PDRB_PENGELUARAN_CHOICES = (
    ("PKRT-01", "PKRT", "Makanan dan minuman tidak beralkohol"),
    ("PKRT-02", "PKRT", "Minuman beralkohol, tembakau, dan narkotika"),
    ("PKRT-03", "PKRT", "Pakaian dan alas kaki"),
    ("PKRT-04", "PKRT", "Perumahan, air, listrik, gas, dan bahan bakar lainnya"),
    ("PKRT-05", "PKRT", "Furniture, perlengkapan rumah tangga, dan pemeliharaan rutin rumah"),
    ("PKRT-06", "PKRT", "Kesehatan"),
    ("PKRT-07", "PKRT", "Transportasi"),
    ("PKRT-08", "PKRT", "Komunikasi"),
    ("PKRT-09", "PKRT", "Rekreasi/hiburan dan kebudayaan"),
    ("PKRT-10", "PKRT", "Pendidikan"),
    ("PKRT-11", "PKRT", "Penyediaan makan minum dan penginapan/akomodasi"),
    ("PKRT-12", "PKRT", "Barang dan jasa lainnya"),
    ("PKP-01", "PKP", "Pelayanan Umum"),
    ("PKP-02", "PKP", "Pertahanan"),
    ("PKP-03", "PKP", "Ketertiban dan Keamanan"),
    ("PKP-04", "PKP", "Ekonomi"),
    ("PKP-05", "PKP", "Perlindungan Lingkungan Hidup"),
    ("PKP-06", "PKP", "Perumahan dan Fasilitas Umum"),
    ("PKP-07", "PKP", "Kesehatan"),
    ("PKP-08", "PKP", "Pariwisata dan Budaya"),
    ("PKP-09", "PKP", "Agama"),
    ("PKP-10", "PKP", "Pendidikan"),
    ("PKP-11", "PKP", "Perlindungan Sosial"),
    ("PMTB-01", "PMTB", "Bangunan dan Tempat Tinggal"),
    ("PMTB-02", "PMTB", "Mesin dan Perlengkapan"),
    ("PMTB-03", "PMTB", "Aset Biologis yang Dibudidayakan"),
    ("PMTB-04", "PMTB", "Produk Kekayaan Intelektual"),
    ("PMTB-05", "PMTB", "Biaya Pemindahan Kepemilikan (Atas Aset Tidak Diproduksi)"),
    ("PKLNPRT-01", "PKLNPRT", "Perumahan"),
    ("PKLNPRT-02", "PKLNPRT", "Kesehatan"),
    ("PKLNPRT-03", "PKLNPRT", "Rekreasi dan Kebudayaan"),
    ("PKLNPRT-04", "PKLNPRT", "Pendidikan"),
    ("PKLNPRT-05", "PKLNPRT", "Perlindungan Sosial"),
    ("PKLNPRT-06", "PKLNPRT", "Keagamaan"),
    ("PKLNPRT-07", "PKLNPRT", "Lingkungan Hidup"),
    ("PKLNPRT-08", "PKLNPRT", "Partai Politik, Organisasi Buruh dan Profesional"),
    ("PKLNPRT-09", "PKLNPRT", "Jasa Lainnya"),
    ("PI-01", "PI", "Bahan Baku dan Penolong"),
    ("PI-02", "PI", "Barang Dalam Proses (Work in Progress)"),
    ("PI-03", "PI", "Barang Jadi"),
    ("PI-04", "PI", "Barang untuk Dijual Kembali (Goods for Resale)"),
)

PDRB_PENGELUARAN_LABELS = {
    code: label for code, _parent_code, label in PDRB_PENGELUARAN_CHOICES
}
PDRB_PENGELUARAN_PARENT_BY_CODE = {
    code: parent_code for code, parent_code, _label in PDRB_PENGELUARAN_CHOICES
}
PDRB_PENGELUARAN_CODE_ORDER = {
    code: index for index, (code, _parent_code, _label) in enumerate(PDRB_PENGELUARAN_CHOICES)
}


class PDRBPengeluaranClassifier(Protocol):
    def classify(self, content: str | None, title: str | None = None) -> str | None:
        ...


def build_pdrb_pengeluaran_code(parent_code: str, ordinal: int) -> str:
    """Bangun kode leaf-level yang stabil untuk taxonomy PDRB pengeluaran."""
    return f"{parent_code}-{int(ordinal):02d}"


def get_pdrb_pengeluaran_parent_code(raw_code: str | None) -> str | None:
    """Ambil parent code dari leaf code atau nilai terformat DB."""
    normalized = str(raw_code or "").strip()
    if not normalized or normalized in {"Tidak Relevan", "—"}:
        return None

    code_only = normalized.split("/", 1)[0].strip().upper()
    if "-" not in code_only:
        return None
    parent_code = code_only.split("-", 1)[0]
    return parent_code if parent_code in PDRB_PENGELUARAN_PARENT_LABELS else None


def format_pdrb_pengeluaran_hasil(code: str | None) -> str | None:
    """Format leaf code ke bentuk yang disimpan/dikirim ke frontend."""
    if not code:
        return None

    normalized = str(code).strip()
    if not normalized:
        return None

    if normalized in {"Tidak Relevan", "—"}:
        return normalized

    normalized_upper = normalized.upper()
    label = PDRB_PENGELUARAN_LABELS.get(normalized_upper)
    if label:
        return f"{normalized_upper}/{label}"

    return normalized


def load_pdrb_pengeluaran_llm_classifier(
    supabase_client,
    embed_client,
    llm_client,
    llm_model: str,
) -> PDRBPengeluaranClassifier | None:
    """Buat instance classifier PDRB pengeluaran berbasis LLM + embedding."""
    try:
        from ai.pdrb_pengeluaran_classifier import PDRBPengeluaranClassifierLLM
    except Exception as exc:
        print(f"[PDRB Pengeluaran] Gagal import classifier: {exc}")
        return None

    if supabase_client is None:
        print("[PDRB Pengeluaran] Supabase client tidak tersedia.")
        return None
    if embed_client is None:
        print("[PDRB Pengeluaran] Embedding client tidak tersedia.")
        return None
    if llm_client is None:
        print("[PDRB Pengeluaran] LLM client tidak tersedia.")
        return None

    try:
        classifier = PDRBPengeluaranClassifierLLM(
            supabase_client=supabase_client,
            embed_client=embed_client,
            llm_client=llm_client,
            llm_model=llm_model,
            top_k=7,
        )
        print(f"[PDRB Pengeluaran] LLM classifier aktif (model: {llm_model}).")
        return classifier
    except Exception as exc:
        print(f"[PDRB Pengeluaran] Gagal inisialisasi classifier: {exc}")
        return None


def predict_pdrb_pengeluaran_label(
    content: str | None,
    classifier: PDRBPengeluaranClassifier | None,
    title: str | None = None,
) -> str | None:
    """Prediksi label PDRB pengeluaran dan kembalikan dalam format simpan DB."""
    if classifier is None:
        return None
    if not content and not title:
        return None

    content_clean = (content or "").strip()
    title_clean = (title or "").strip()
    if not content_clean and not title_clean:
        return None

    try:
        code = classifier.classify(content_clean, title=title_clean)
    except Exception as exc:
        print(f"[PDRB Pengeluaran] Gagal prediksi: {exc}")
        return None

    if not code:
        return None

    return format_pdrb_pengeluaran_hasil(code)


__all__ = [
    "PDRB_PENGELUARAN_CHOICES",
    "PDRB_PENGELUARAN_CODE_ORDER",
    "PDRB_PENGELUARAN_LABELS",
    "PDRB_PENGELUARAN_PARENT_BY_CODE",
    "PDRB_PENGELUARAN_PARENT_LABELS",
    "PDRB_PENGELUARAN_REFERENCE_SPECS",
    "build_pdrb_pengeluaran_code",
    "format_pdrb_pengeluaran_hasil",
    "get_pdrb_pengeluaran_parent_code",
    "load_pdrb_pengeluaran_llm_classifier",
    "predict_pdrb_pengeluaran_label",
]
