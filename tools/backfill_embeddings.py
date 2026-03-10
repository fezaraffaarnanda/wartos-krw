"""
tools/backfill_embeddings.py — Backfill embedding untuk semua artikel existing

Jalankan sekali untuk meng-embed 719 artikel yang sudah ada di database:
    python tools/backfill_embeddings.py

Aman untuk di-restart: hanya memproses artikel yang embedding IS NULL.
"""

import os
import sys
import time

# Tambah root project ke path agar bisa import dari root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client
from embeddings import batch_embed_articles, _build_embedding_client

# ── Config ─────────────────────────────────────────────────────────────────────

_BATCH_SIZE = 50          # Jumlah artikel per batch API call
_SLEEP_BETWEEN = 0.5      # Jeda antar batch (detik)


def main():
    # ── Init Supabase ──────────────────────────────────────────────────────────
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        print("[Backfill] ERROR: SUPABASE_URL atau SUPABASE_KEY tidak ditemukan.")
        sys.exit(1)

    supabase = create_client(url, key)

    # ── Hitung artikel yang belum di-embed ────────────────────────────────────
    result_total = (
        supabase.table("berita")
        .select("id", count="exact")
        .is_("embedding", "null")
        .execute()
    )
    total_null = result_total.count or 0
    print(f"[Backfill] Ditemukan {total_null} artikel belum memiliki embedding.")

    if total_null == 0:
        print("[Backfill] Semua artikel sudah di-embed. Tidak ada yang perlu diproses.")
        return

    # ── Init OpenAI client sekali ──────────────────────────────────────────────
    embed_client = _build_embedding_client()

    processed  = 0
    failed     = 0
    start_time = time.time()

    # ── Proses dalam batch (offset pagination) ────────────────────────────────
    offset = 0
    while True:
        # Ambil batch artikel yang belum di-embed
        rows = (
            supabase.table("berita")
            .select("id, title, tags, content")
            .is_("embedding", "null")
            .order("id")
            .limit(_BATCH_SIZE)
            .execute()
        )
        articles = rows.data or []
        if not articles:
            break

        ids = [a["id"] for a in articles]
        print(f"[Backfill] Memproses {len(articles)} artikel (ID {ids[0]}–{ids[-1]})...")

        # Generate embedding untuk semua artikel dalam batch ini
        embeddings = batch_embed_articles(articles, client=embed_client)

        # Update ke Supabase satu per satu (update by ID)
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
            except Exception as exc:
                print(f"[Backfill] ⚠ Gagal update DB artikel ID={article['id']}: {exc}")
                failed += 1

        elapsed = time.time() - start_time
        print(
            f"[Backfill] Progress: {processed}/{total_null} selesai"
            f" | Gagal: {failed}"
            f" | Waktu: {elapsed:.1f}s"
        )

        # Jeda antar batch
        time.sleep(_SLEEP_BETWEEN)

        # Safety: kalau semua batch gagal (loop infinite prevention)
        if not any(e is not None for e in embeddings):
            print("[Backfill] ERROR: Semua embedding gagal. Hentikan proses.")
            break

    # ── Summary ────────────────────────────────────────────────────────────────
    elapsed_total = time.time() - start_time
    print()
    print("=" * 60)
    print(f"[Backfill] SELESAI")
    print(f"  Berhasil di-embed : {processed} artikel")
    print(f"  Gagal             : {failed} artikel")
    print(f"  Total waktu       : {elapsed_total:.1f} detik")
    print("=" * 60)

    if failed > 0:
        print(f"[Backfill] Ada {failed} artikel yang gagal. Jalankan ulang untuk retry.")


if __name__ == "__main__":
    main()
