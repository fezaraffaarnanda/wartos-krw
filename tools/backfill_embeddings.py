"""
tools/backfill_embeddings.py — Backfill / regenerasi embedding untuk artikel existing

Mode default (tanpa flag):
    Hanya memproses artikel yang embedding IS NULL.
    python tools/backfill_embeddings.py

Mode force (--force):
    Memproses SEMUA artikel — embedding di-overwrite.
    Gunakan setelah ganti model embedding (mis. OpenAI → Gemini).
    python tools/backfill_embeddings.py --force

=== RATE LIMIT Gemini Embedding API (Free Tier) ===
    RPM : 100 request per menit
    TPM : 30.000 token per menit
    RPD : 1.000 request per hari

  Estimasi token per artikel : ~700 token (title + tags + KBLI + 2000 char konten)
  Batch size 25 artikel       : 25 × 700 = ~17.500 token per request
  Delay 65 detik antar batch  : 17.500 / 65s × 60 ≈ 16.000 TPM  ← aman di bawah 30k
  ~800 artikel                : 32 batch × 65s ≈ 35 menit total

Aman untuk di-restart: mode default hanya memproses artikel yang belum ter-embed.
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

# 25 artikel × ~700 token = ~17.500 token per request — aman di bawah 30k TPM/menit
_BATCH_SIZE    = 25

# 65 detik antar batch → 0.9 RPM (aman << 100 RPM), ~16k TPM (aman << 30k TPM)
_SLEEP_BETWEEN = 65

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

    # Estimasi durasi berdasarkan rate limit
    n_batches = (total + _BATCH_SIZE - 1) // _BATCH_SIZE
    est_minutes = (n_batches * _SLEEP_BETWEEN) / 60
    print(f"[Backfill] Batch size : {_BATCH_SIZE} artikel/batch")
    print(f"[Backfill] Delay      : {_SLEEP_BETWEEN}s antar batch (rate limit Gemini free tier)")
    print(f"[Backfill] Estimasi   : {n_batches} batch x {_SLEEP_BETWEEN}s ~= {est_minutes:.0f} menit")
    print("[Backfill] Mulai proses...")
    print()

    # ── Init Gemini embedding client sekali ────────────────────────────────────
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
        batch_num = (processed // _BATCH_SIZE) + 1
        print(f"[Backfill] Batch {batch_num}/{n_batches}: {len(articles)} artikel (ID {ids[0]}-{ids[-1]})...")

        # Generate embedding untuk semua artikel dalam batch ini
        # _prepare_text() sudah menyertakan kbli + date_parsed dari row DB
        embeddings = batch_embed_articles(articles, client=embed_client)

        # Update ke Supabase satu per satu (update by ID)
        batch_ok = 0
        for article, embedding in zip(articles, embeddings):
            if embedding is None:
                print(f"[Backfill] SKIP: Gagal embed artikel ID={article['id']} - lewati.")
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
        remaining = max(0, (n_batches - batch_num) * _SLEEP_BETWEEN)
        print(
            f"[Backfill] Progress : {processed}/{total} berhasil"
            f" | Gagal: {failed}"
            f" | Waktu: {elapsed:.0f}s"
            f" | Estimasi sisa: {remaining:.0f}s"
        )

        # Jeda antar batch — menghormati rate limit Gemini free tier
        if articles:   # hanya sleep jika ada artikel yang diproses
            print(f"[Backfill] Menunggu {_SLEEP_BETWEEN}s (rate limit)...")
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
