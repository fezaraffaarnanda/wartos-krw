"""
tools/backfill_kbli.py — Backfill kolom KBLI untuk berita existing.

Jalankan:
    python tools/backfill_kbli.py

Script ini aman diulang: hanya memproses berita dengan kolom `kbli` yang masih NULL.
"""

import os
import sys
import time

# Tambah root project ke path agar bisa import module dari root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from supabase import create_client

from kbli_utils import load_kbli_predictor, predict_kbli_label

load_dotenv()


# ── Config ─────────────────────────────────────────────────────────────────────

_BATCH_SIZE = 100
_SLEEP_BETWEEN = 0.2


def main():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    model_dir = os.getenv("KBLI_MODEL_DIR", "model_kbli")

    if not url or not key:
        print("[Backfill KBLI] ERROR: SUPABASE_URL atau SUPABASE_KEY tidak ditemukan.")
        sys.exit(1)

    predictor = load_kbli_predictor(model_dir)
    if predictor is None:
        print("[Backfill KBLI] ERROR: Model KBLI gagal dimuat. Proses dihentikan.")
        sys.exit(1)

    supabase = create_client(url, key)

    result_total = (
        supabase.table("berita")
        .select("id", count="exact")
        .is_("kbli", "null")
        .execute()
    )
    total_null = result_total.count or 0
    print(f"[Backfill KBLI] Ditemukan {total_null} berita dengan kbli NULL.")

    if total_null == 0:
        print("[Backfill KBLI] Tidak ada data yang perlu di-backfill.")
        return

    processed = 0
    skipped = 0
    failed = 0
    started_at = time.time()

    while True:
        rows = (
            supabase.table("berita")
            .select("id, title, content")
            .is_("kbli", "null")
            .order("id")
            .limit(_BATCH_SIZE)
            .execute()
        )
        articles = rows.data or []

        if not articles:
            break

        first_id = articles[0].get("id")
        last_id = articles[-1].get("id")
        print(f"[Backfill KBLI] Memproses {len(articles)} berita (ID {first_id}–{last_id})...")

        updated_this_batch = 0

        for article in articles:
            article_id = article.get("id")
            prediction_text = article.get("content") or article.get("title")
            label = predict_kbli_label(prediction_text, predictor)

            if not label:
                skipped += 1
                continue

            try:
                (
                    supabase.table("berita")
                    .update({"kbli": label})
                    .eq("id", article_id)
                    .execute()
                )
                processed += 1
                updated_this_batch += 1
            except Exception as exc:
                print(f"[Backfill KBLI] Gagal update ID={article_id}: {exc}")
                failed += 1

        elapsed = time.time() - started_at
        print(
            f"[Backfill KBLI] Progress: {processed}/{total_null}"
            f" | Skip: {skipped}"
            f" | Gagal: {failed}"
            f" | Waktu: {elapsed:.1f}s"
        )

        time.sleep(_SLEEP_BETWEEN)

        if updated_this_batch == 0:
            print("[Backfill KBLI] Tidak ada update pada batch ini. Proses dihentikan agar tidak looping.")
            break

    total_time = time.time() - started_at
    print()
    print("=" * 60)
    print("[Backfill KBLI] SELESAI")
    print(f"  Berhasil diupdate : {processed}")
    print(f"  Skip (tanpa hasil): {skipped}")
    print(f"  Gagal update      : {failed}")
    print(f"  Total waktu       : {total_time:.1f} detik")
    print("=" * 60)


if __name__ == "__main__":
    main()
