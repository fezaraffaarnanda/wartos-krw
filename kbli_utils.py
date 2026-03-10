"""Utilitas integrasi prediksi KBLI untuk app dan script backfill."""

KBLI_KEY_MAPPING = {
    "A1": "Pertanian, Peternakan, Perburuan dan Jasa Pertanian",
    "A2": "Kehutanan dan Penebangan Kayu",
    "A3": "Perikanan",
    "B1": "Pertambangan Migas",
    "B2": "Pertambangan Batu Bara",
    "B3": "Pertambangan Bijih Logam",
    "B4": "Pertambangan dan Penggalian Lainnya",
    "C1": "Industri Migas",
    "C2": "Industri Makan Minum (CPO, padi,dll)",
    "C3": "Industri Kimia dan Farmasi",
    "C4": "Industri Barang Galian",
    "C5": "Industri selain 1-4",
    "D": "Pengadaan Listrik dan Gas",
    "E": "Pengadaan Air, Pengelolaan Sampah, Limbah dan Daur Ulang",
    "F": "Konstruksi",
    "G": "Perdagangan Besar & Eceran Reparasi Mobil & Sepeda Motor",
    "H1": "Transportasi Darat",
    "H2": "Transportasi Udara",
    "H3": "Transportasi Laut",
    "H4": "Penyeberangan/ASDP",
    "H5": "Penunjang Angkutan dan Pergudangan",
    "I": "Penyediaan Akomodasi dan Makan Minum",
    "J": "Informasi dan Komunikasi",
    "K": "Jasa Keuangan dan Asuransi",
    "L": "Real Estate",
    "MN": "Jasa Perusahaan",
    "O": "Administrasi Pemerintahan Pertahanan & Jaminan Sosial Wajib",
    "P": "Jasa Pendidikan",
    "Q": "Jasa Kesehatan dan Kegiatan Sosial",
    "RSTU": "Jasa lainnya",
    "KE": "Kemiskinan",
    "PG": "Pengangguran",
}


def format_kbli_hasil(kode: str | None, confidence_low: bool = False) -> str | None:
    """Format hasil KBLI ke bentuk yang ditampilkan di tabel dashboard."""
    if not kode:
        return None

    normalized = str(kode).strip().upper()
    if not normalized:
        return None

    if confidence_low:
        return f"{normalized} (Tingkat Kepercayaan Model Rendah)"

    deskripsi = KBLI_KEY_MAPPING.get(normalized)
    if not deskripsi:
        return normalized
    return f"{normalized}/{deskripsi}"


def load_kbli_predictor(model_dir: str = "model_kbli"):
    """Load model predictor KBLI. Return None jika gagal."""
    try:
        from predictor_kbli import KBLIPredictor
    except Exception as exc:
        print(f"[KBLI] Gagal import predictor_kbli: {exc}")
        return None

    try:
        predictor = KBLIPredictor(model_dir)
        print(f"[KBLI] Model KBLI aktif dari folder '{model_dir}'.")
        return predictor
    except Exception as exc:
        print(f"[KBLI] Gagal load model KBLI dari '{model_dir}': {exc}")
        return None


def predict_kbli_label(content: str | None, predictor, threshold: float = 0.3) -> str | None:
    """Prediksi label KBLI untuk konten berita dan format hasilnya."""
    if predictor is None:
        return None

    if not content or not str(content).strip():
        return None

    try:
        hasil = predictor.prediksi(content, threshold=threshold)
    except Exception as exc:
        print(f"[KBLI] Gagal prediksi konten berita: {exc}")
        return None

    kategori = str(hasil.get("kategori", "")).strip()
    if not kategori:
        return None

    if kategori == "Tidak Relevan":
        kandidat = str(hasil.get("kandidat", "")).strip()
        return format_kbli_hasil(kandidat, confidence_low=True)

    return format_kbli_hasil(kategori, confidence_low=False)
