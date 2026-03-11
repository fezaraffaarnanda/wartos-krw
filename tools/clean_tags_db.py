"""
tools/clean_tags_db.py — Bersihkan tag existing di database

Menerapkan clean_tags() pada semua artikel yang memiliki tag,
menghapus nama daerah (tegal, dll.), stop words, tag terlalu pendek, dll.

Aman untuk dijalankan berulang kali — hanya update baris yang berubah.

Cara pakai:
    python tools/clean_tags_db.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client
from core.utils import clean_tags

# ── Config ─────────────────────────────────────────────────────────────────────

_FETCH_BATCH = 500   # ambil sekaligus, kurangi round-trips


def main():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        print("[CleanTags] ERROR: SUPABASE_URL atau SUPABASE_KEY tidak ditemukan.")
        sys.exit(1)

    supabase = create_client(url, key)

    # Ambil semua artikel dengan tags sekaligus (id + tags saja, ringan)
    print("[CleanTags] Mengambil data tag dari database...")
    all_rows = []
    offset = 0
    while True:
        res = (
            supabase.table("berita")
            .select("id, tags")
            .not_.is_("tags", "null")
            .order("id")
            .range(offset, offset + _FETCH_BATCH - 1)
            .execute()
        )
        batch = res.data or []
        if not batch:
            break
        all_rows.extend(batch)
        offset += _FETCH_BATCH
        if len(batch) < _FETCH_BATCH:
            break

    total = len(all_rows)
    print(f"[CleanTags] {total} artikel memiliki tag — proses cleaning...")

    # Hitung yang perlu diupdate
    to_update = []
    for row in all_rows:
        original = row["tags"] or ""
        cleaned  = clean_tags(original)
        if cleaned != original:
            to_update.append({"id": row["id"], "cleaned": cleaned})

    print(f"[CleanTags] {len(to_update)} artikel perlu diupdate, {total - len(to_update)} sudah bersih.")

    if not to_update:
        print("[CleanTags] Tidak ada yang perlu diupdate.")
        return

    # Update satu per satu (Supabase tidak support bulk update)
    updated   = 0
    failed    = 0
    start_time = time.time()

    for i, item in enumerate(to_update, 1):
        try:
            supabase.table("berita").update({"tags": item["cleaned"]}).eq("id", item["id"]).execute()
            updated += 1
        except Exception as exc:
            print(f"[CleanTags] Gagal update id={item['id']}: {exc}")
            failed += 1

        if i % 50 == 0 or i == len(to_update):
            elapsed = time.time() - start_time
            print(f"[CleanTags] {i}/{len(to_update)} diupdate | Waktu: {elapsed:.1f}s")

    elapsed_total = time.time() - start_time
    print()
    print("=" * 60)
    print("[CleanTags] SELESAI")
    print(f"  Total artikel   : {total}")
    print(f"  Tag diperbarui  : {updated} artikel")
    print(f"  Gagal           : {failed} artikel")
    print(f"  Total waktu     : {elapsed_total:.1f} detik")
    print("=" * 60)


if __name__ == "__main__":
    main()
