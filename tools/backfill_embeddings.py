"""
tools/backfill_embeddings.py — Backfill / regenerasi embedding untuk artikel existing

Mode default (tanpa flag):
    Hanya memproses artikel yang embedding IS NULL.
    python tools/backfill_embeddings.py

Mode force (--force):
    Memproses SEMUA artikel — embedding di-overwrite.
    Gunakan setelah perubahan format embedding (misalnya penambahan KBLI + tanggal).
    python tools/backfill_embeddings.py --force

Aman untuk di-restart pada mode default: hanya memproses artikel yang belum ter-embed.
"""

import argparse
import os
import sys
import time

# Tambah root project ke path agar bisa import dari root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client
from core.embeddings import batch_embed_articles, _build_embedding_client

# ── Config ─────────────────────────────────────────────────────────────────────

_BATCH_SIZE    = 50    # Jumlah artikel per batch API call
_SLEEP_BETWEEN = 0.5   # Jeda antar batch (detik)

# Kolom yang di-select — mencakup semua field yang dipakai _prepare_text()
_SELECT_COLS = "id, title, tags, content, kbli, date, date_parsed"


def main(force: bool = False):
    # ── Init Supabase ──────────────────────────────────────────────────────────
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        print("[Backfill] ERROR: SUPABASE_URL atau SUPABASE_KEY tidak ditemukan.")
        sys.exit(1)

    supabase = create_client(url, key)

    # ── Hitung artikel yang akan diproses ─────────────────────────────────────
    if force:
        result_total = supabase.table("berita").select("id", count="exact").execute()
        total = result_total.count or 0
        print(f"[Backfill] Mode FORCE: akan meregenerasi embedding untuk SEMUA {total} artikel.")
    else:
        result_total = (
            supabase.table("berita")
            .select("id", count="exact")
            .is_("embedding", "null")
            .execute()
        )
        total = result_total.count or 0
        print(f"[Backfill] Ditemukan {total} artikel belum memiliki embedding.")

    if total == 0:
        print("[Backfill] Tidak ada artikel yang perlu diproses.")
        return

    # ── Init OpenAI client sekali ──────────────────────────────────────────────
    embed_client = _build_embedding_client()

    processed  = 0
    failed     = 0
    start_time = time.time()

    # ── Proses dalam batch ────────────────────────────────────────────────────
    # Mode default: filter embedding IS NULL, offset tidak bergerak karena row yang
    #               sudah di-update keluar dari result set query berikutnya.
    # Mode force:   range-based offset karena tidak ada filter — semua row ikut diproses.
    offset = 0
    while True:
        if force:
            rows_result = (
                supabase.table("berita")
                .select(_SELECT_COLS)
                .order("id")
                .range(offset, offset + _BATCH_SIZE - 1)
                .execute()
            )
        else:
            rows_result = (
                supabase.table("berita")
                .select(_SELECT_COLS)
                .is_("embedding", "null")
                .order("id")
                .limit(_BATCH_SIZE)
                .execute()
            )

        articles = rows_result.data or []
        if not articles:
            break

        ids = [a["id"] for a in articles]
        print(f"[Backfill] Memproses {len(articles)} artikel (ID {ids[0]}–{ids[-1]})...")

        # Generate embedding untuk semua artikel dalam batch ini
        # _prepare_text() sudah menyertakan kbli + date_parsed dari row DB
        embeddings = batch_embed_articles(articles, client=embed_client)

        # Update ke Supabase satu per satu (update by ID)
        batch_ok = 0
        for article, embedding in zip(articles, embeddings):
            if embedding is None:
                print(f"[Backfill] SKIP: Gagal embed artikel ID={article['id']} — lewati.")
                failed += 1
                continue

            try:
                supabase.table("berita").update(
                    {"embedding": embedding}
                ).eq("id", article["id"]).execute()
                processed += 1
                batch_ok  += 1
            except Exception as exc:
                print(f"[Backfill] Gagal update DB artikel ID={article['id']}: {exc}")
                failed += 1

        elapsed = time.time() - start_time
        print(
            f"[Backfill] Progress: {processed}/{total} selesai"
            f" | Gagal: {failed}"
            f" | Waktu: {elapsed:.1f}s"
        )

        # Jeda antar batch
        time.sleep(_SLEEP_BETWEEN)

        if force:
            offset += _BATCH_SIZE
        else:
            # Safety: kalau semua batch gagal (loop infinite prevention)
            if batch_ok == 0:
                print("[Backfill] ERROR: Semua embedding gagal. Hentikan proses.")
                break

    # ── Summary ────────────────────────────────────────────────────────────────
    elapsed_total = time.time() - start_time
    print()
    print("=" * 60)
    print("[Backfill] SELESAI")
    print(f"  Mode              : {'FORCE (semua artikel)' if force else 'DEFAULT (embedding NULL)'}")
    print(f"  Berhasil di-embed : {processed} artikel")
    print(f"  Gagal             : {failed} artikel")
    print(f"  Total waktu       : {elapsed_total:.1f} detik")
    print("=" * 60)

    if failed > 0:
        print(f"[Backfill] Ada {failed} artikel yang gagal. Jalankan ulang untuk retry.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill / regenerasi vector embedding untuk artikel berita."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerasi ulang embedding untuk SEMUA artikel (bukan hanya yang NULL).",
    )
    args = parser.parse_args()
    main(force=args.force)
