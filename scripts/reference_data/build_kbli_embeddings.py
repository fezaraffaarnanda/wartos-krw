"""
build_kbli_embeddings.py — Populasi tabel kbli_master dari file Excel KBLI 2025.

Skrip ini:
1. Membaca data/reference/kbli_2025_kode_judul_deskripsi.xlsx (22 baris: kode A–V)
2. Menambahkan dua kategori custom: KE (Kemiskinan) dan PG (Pengangguran)
3. Memformat teks embedding untuk setiap KBLI
4. Membuat embedding via Gemini API (1536-dim)
5. Upsert ke tabel kbli_master di Supabase

Jalankan sekali setelah migration_kbli_master.sql berhasil diapply.

Pemakaian:
    python -m scripts.reference_data.build_kbli_embeddings
    python -m scripts.reference_data.build_kbli_embeddings --force   # regenerate semua, termasuk yang sudah ada
"""

import argparse
import os
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

from ai.embeddings import _build_embedding_client, generate_embedding

load_dotenv()


# ── Konstanta ──────────────────────────────────────────────────────────────────

# Panjang maksimal deskripsi yang diikutsertakan dalam teks embedding
# (terlalu panjang = boros token + noise; terlalu pendek = representasi kurang kaya)
_MAX_DESKRIPSI_EMBED = 800

# Delay antar embedding call (detik) untuk menghindari rate limit Gemini free tier
_DELAY_BETWEEN_EMBED = 0.5

# Path file master KBLI
_ROOT_DIR = Path(__file__).resolve().parents[2]
_MASTER_XLSX = _ROOT_DIR / "data" / "reference" / "kbli_2025_kode_judul_deskripsi.xlsx"

# Kategori custom (tidak ada di standar KBLI 2025)
_CUSTOM_KBLI = [
    {
        "kode":     "KE",
        "judul":    "Kemiskinan",
        "deskripsi": (
            "Kondisi kemiskinan penduduk, garis kemiskinan, warga miskin, kemiskinan ekstrem, "
            "bantuan sosial (bansos) berbasis kemiskinan, program pengentasan kemiskinan, "
            "BPS data kemiskinan, persentase penduduk miskin, subsidi kemiskinan."
        ),
    },
    {
        "kode":     "PG",
        "judul":    "Pengangguran",
        "deskripsi": (
            "Angka pengangguran, Tingkat Pengangguran Terbuka (TPT), pencari kerja, "
            "ketenagakerjaan, Pemutusan Hubungan Kerja (PHK), lowongan kerja, "
            "penyerapan tenaga kerja, BPS data ketenagakerjaan, tenaga kerja, angkatan kerja."
        ),
    },
]


def _format_embed_text(kode: str, judul: str, deskripsi: str) -> str:
    """
    Format teks yang akan di-embed untuk satu entri KBLI.

    Format terstruktur agar model embedding dapat menangkap konteks:
    - Kode      : sinyal singkat dan unik per kategori
    - Judul     : frasa ringkas yang merepresentasikan kategori
    - Deskripsi : konteks lebih dalam (dipotong agar tidak terlalu panjang)
    """
    deskripsi_clean = (deskripsi or "").strip()
    if len(deskripsi_clean) > _MAX_DESKRIPSI_EMBED:
        deskripsi_clean = deskripsi_clean[:_MAX_DESKRIPSI_EMBED].rstrip() + "..."

    parts = [f"KBLI {kode}: {judul}"]
    if deskripsi_clean:
        parts.append(deskripsi_clean)

    return "\n\n".join(parts)


def _load_kbli_rows() -> list[dict]:
    """
    Baca file Excel master KBLI dan tambahkan kategori custom.
    Return list of dicts: {kode, judul, deskripsi, embed_text}
    """
    if not os.path.exists(_MASTER_XLSX):
        raise FileNotFoundError(f"File master KBLI tidak ditemukan: {_MASTER_XLSX}")

    df = pd.read_excel(_MASTER_XLSX)
    print(f"[Build] Membaca {len(df)} baris dari {os.path.basename(_MASTER_XLSX)}")

    rows = []
    for _, row in df.iterrows():
        kode     = str(row["Kode"]).strip()
        judul    = str(row["Judul"]).strip()
        deskripsi = str(row.get("Deskripsi") or "").strip()

        if not kode or kode.lower() == "nan":
            continue

        rows.append({
            "kode":       kode,
            "judul":      judul,
            "deskripsi":  deskripsi,
            "embed_text": _format_embed_text(kode, judul, deskripsi),
        })

    # Tambahkan kategori custom
    for custom in _CUSTOM_KBLI:
        rows.append({
            "kode":       custom["kode"],
            "judul":      custom["judul"],
            "deskripsi":  custom["deskripsi"],
            "embed_text": _format_embed_text(
                custom["kode"], custom["judul"], custom["deskripsi"]
            ),
        })
        print(f"[Build] Tambah kategori custom: {custom['kode']} — {custom['judul']}")

    print(f"[Build] Total {len(rows)} entri KBLI (termasuk custom).")
    return rows


def _get_existing_kodes(supabase) -> set[str]:
    """Ambil daftar kode yang sudah ada di tabel kbli_master."""
    try:
        result = supabase.table("kbli_master").select("kode").execute()
        return {r["kode"] for r in (result.data or [])}
    except Exception as exc:
        print(f"[Build] Gagal query kbli_master: {exc}")
        return set()


def main():
    parser = argparse.ArgumentParser(description="Populasi tabel kbli_master dari Excel KBLI 2025.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate embedding untuk semua KBLI, termasuk yang sudah ada.",
    )
    args = parser.parse_args()

    # Inisialisasi klien
    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_KEY", "")
    if not supabase_url or not supabase_key:
        print("[Build] ERROR: SUPABASE_URL atau SUPABASE_KEY tidak tersedia di .env")
        sys.exit(1)

    try:
        embed_client = _build_embedding_client()
    except ValueError as exc:
        print(f"[Build] ERROR: {exc}")
        sys.exit(1)

    supabase = create_client(supabase_url, supabase_key)

    # Baca data
    rows = _load_kbli_rows()

    # Cek entri yang sudah ada (skip jika tidak --force)
    existing = set() if args.force else _get_existing_kodes(supabase)
    if existing and not args.force:
        print(f"[Build] {len(existing)} kode sudah ada di DB — akan di-skip.")
        print(f"[Build] Gunakan --force untuk regenerate semuanya.")

    # Generate embedding dan upsert satu per satu
    ok_count   = 0
    skip_count = 0
    fail_count = 0

    for i, row in enumerate(rows, 1):
        kode  = row["kode"]
        judul = row["judul"]

        if kode in existing and not args.force:
            print(f"[Build] [{i:02d}/{len(rows)}] {kode} — skip (sudah ada)")
            skip_count += 1
            continue

        print(f"[Build] [{i:02d}/{len(rows)}] {kode} ({judul[:50]}) — generate embedding...")

        embedding = generate_embedding(row["embed_text"], client=embed_client)
        if embedding is None:
            print(f"[Build] WARNING: Gagal generate embedding untuk {kode} — skip.")
            fail_count += 1
            continue

        try:
            supabase.table("kbli_master").upsert({
                "kode":      kode,
                "judul":     judul,
                "deskripsi": row["deskripsi"],
                "embedding": embedding,
            }).execute()
            ok_count += 1
            print(f"[Build]   -> Berhasil upsert {kode}.")
        except Exception as exc:
            print(f"[Build] ERROR: Gagal upsert {kode}: {exc}")
            fail_count += 1

        # Rate limit protection
        if i < len(rows):
            time.sleep(_DELAY_BETWEEN_EMBED)

    print()
    print("=" * 50)
    print(f"[Build] Selesai. Berhasil: {ok_count} | Skip: {skip_count} | Gagal: {fail_count}")
    print("=" * 50)

    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
