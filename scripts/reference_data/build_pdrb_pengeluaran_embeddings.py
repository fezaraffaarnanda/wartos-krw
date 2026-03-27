"""
Bangun master embedding untuk taxonomy PDRB pengeluaran dari file referensi Excel.

Pemakaian:
    python -m scripts.reference_data.build_pdrb_pengeluaran_embeddings
    python -m scripts.reference_data.build_pdrb_pengeluaran_embeddings --force
"""

import argparse
import os
import sys
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

from ai.embeddings import _build_embedding_client, generate_embedding
from ai.pdrb_pengeluaran import (
    PDRB_PENGELUARAN_LABELS,
    PDRB_PENGELUARAN_PARENT_LABELS,
    PDRB_PENGELUARAN_REFERENCE_SPECS,
    build_pdrb_pengeluaran_code,
)

load_dotenv()

_ROOT_DIR = Path(__file__).resolve().parents[2]
_REFERENCE_DIR = _ROOT_DIR / "data" / "reference" / "pdrb_pengeluaran"
_MAX_DESKRIPSI_EMBED = 900
_DELAY_BETWEEN_EMBED = 0.15


def _format_embed_text(parent_code: str, kode: str, judul: str, deskripsi: str) -> str:
    parent_label = PDRB_PENGELUARAN_PARENT_LABELS[parent_code]
    deskripsi_clean = (deskripsi or "").strip()
    if len(deskripsi_clean) > _MAX_DESKRIPSI_EMBED:
        deskripsi_clean = deskripsi_clean[:_MAX_DESKRIPSI_EMBED].rstrip() + "..."

    return "\n\n".join(
        part
        for part in (
            f"PDRB Pengeluaran {kode}",
            f"Kelompok: {parent_label}",
            f"Komponen: {judul}",
            deskripsi_clean,
        )
        if part
    )


def _load_reference_rows() -> list[dict]:
    rows: list[dict] = []
    for spec in PDRB_PENGELUARAN_REFERENCE_SPECS:
        path = _REFERENCE_DIR / spec["file_name"]
        if not path.exists():
            raise FileNotFoundError(f"File referensi tidak ditemukan: {path}")

        df = pd.read_excel(path)
        df_rows = df.iloc[1:].reset_index(drop=True)
        parent_code = spec["parent_code"]
        has_division = bool(spec["has_division"])

        for index, row in df_rows.iterrows():
            judul_idx = 1 if has_division else 0
            deskripsi_idx = 2 if has_division else 1

            judul = str(row.iloc[judul_idx] or "").strip()
            deskripsi = str(row.iloc[deskripsi_idx] or "").strip()
            if not judul or judul.lower() == "nan":
                continue

            kode = build_pdrb_pengeluaran_code(parent_code, index + 1)
            expected_label = PDRB_PENGELUARAN_LABELS.get(kode)
            if expected_label and expected_label != judul:
                raise ValueError(
                    f"Label referensi berubah untuk {kode}: '{judul}' != '{expected_label}'"
                )

            rows.append(
                {
                    "kode": kode,
                    "parent_code": parent_code,
                    "parent_judul": PDRB_PENGELUARAN_PARENT_LABELS[parent_code],
                    "judul": expected_label or judul,
                    "deskripsi": deskripsi,
                    "sort_order": len(rows) + 1,
                    "embed_text": _format_embed_text(
                        parent_code,
                        kode,
                        expected_label or judul,
                        deskripsi,
                    ),
                }
            )

    return rows


def _get_existing_codes(supabase) -> set[str]:
    try:
        result = supabase.table("pdrb_pengeluaran_master").select("kode").execute()
        return {row["kode"] for row in (result.data or []) if row.get("kode")}
    except Exception as exc:
        print(f"[Build PDRB Pengeluaran] Gagal query master: {exc}")
        return set()


def main():
    parser = argparse.ArgumentParser(description="Bangun master embedding PDRB pengeluaran.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate semua entri meski sudah ada di DB.",
    )
    args = parser.parse_args()

    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_KEY", "")
    if not supabase_url or not supabase_key:
        print("[Build PDRB Pengeluaran] ERROR: SUPABASE_URL atau SUPABASE_KEY tidak tersedia.")
        sys.exit(1)

    try:
        embed_client = _build_embedding_client()
    except ValueError as exc:
        print(f"[Build PDRB Pengeluaran] ERROR: {exc}")
        sys.exit(1)

    supabase = create_client(supabase_url, supabase_key)
    rows = _load_reference_rows()
    existing = set() if args.force else _get_existing_codes(supabase)

    ok_count = 0
    skip_count = 0
    fail_count = 0

    print(f"[Build PDRB Pengeluaran] Total referensi: {len(rows)}")

    for index, row in enumerate(rows, start=1):
        kode = row["kode"]
        if kode in existing and not args.force:
            print(f"[Build PDRB Pengeluaran] [{index:02d}/{len(rows)}] {kode} - skip")
            skip_count += 1
            continue

        print(f"[Build PDRB Pengeluaran] [{index:02d}/{len(rows)}] {kode} - generate embedding...")
        embedding = generate_embedding(row["embed_text"], client=embed_client)
        if embedding is None:
            print(f"[Build PDRB Pengeluaran] WARNING: gagal generate embedding untuk {kode}.")
            fail_count += 1
            continue

        try:
            supabase.table("pdrb_pengeluaran_master").upsert(
                {
                    "kode": row["kode"],
                    "parent_code": row["parent_code"],
                    "parent_judul": row["parent_judul"],
                    "judul": row["judul"],
                    "deskripsi": row["deskripsi"],
                    "sort_order": row["sort_order"],
                    "embedding": embedding,
                }
            ).execute()
            ok_count += 1
        except Exception as exc:
            print(f"[Build PDRB Pengeluaran] ERROR: gagal upsert {kode}: {exc}")
            fail_count += 1

        if index < len(rows):
            time.sleep(_DELAY_BETWEEN_EMBED)

    print()
    print("=" * 60)
    print(
        f"[Build PDRB Pengeluaran] Selesai. Berhasil: {ok_count} | "
        f"Skip: {skip_count} | Gagal: {fail_count}"
    )
    print("=" * 60)

    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
