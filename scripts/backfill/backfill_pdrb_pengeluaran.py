"""
Backfill kolom PDRB pengeluaran secara paralel.

Pemakaian:
    python -m scripts.backfill.backfill_pdrb_pengeluaran
    python -m scripts.backfill.backfill_pdrb_pengeluaran --workers 20
    python -m scripts.backfill.backfill_pdrb_pengeluaran --dry-run
"""

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
from supabase import create_client

from ai.embeddings import _build_embedding_client, batch_embed_texts
from ai.pdrb_pengeluaran import format_pdrb_pengeluaran_hasil
from ai.pdrb_pengeluaran_classifier import PDRBPengeluaranClassifierLLM
from clients.llm import build_chat_client

load_dotenv()


def _is_kbli_irrelevant(value: str | None) -> bool:
    normalized = str(value or "").strip()
    return not normalized or normalized in {"Tidak Relevan", "—"}


def _make_embed_text(article: dict) -> str:
    title = (article.get("title") or "").strip()
    content = (article.get("content") or "").strip()
    parts = []
    if title:
        parts.append(f"Judul: {title}")
    if content:
        parts.append(f"Konten: {content[:2200]}")
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Backfill PDRB pengeluaran secara paralel.")
    parser.add_argument("--workers", type=int, default=18, help="Jumlah thread LLM.")
    parser.add_argument("--db-batch", type=int, default=50, help="Jumlah update DB per batch.")
    parser.add_argument("--dry-run", action="store_true", help="Preview tanpa update DB.")
    args = parser.parse_args()

    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        print("ERROR: SUPABASE_URL / SUPABASE_KEY tidak ditemukan di .env")
        sys.exit(1)

    supabase = create_client(url, key)

    try:
        embed_client = _build_embedding_client()
    except ValueError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    try:
        llm_client, llm_model = build_chat_client()
    except ValueError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    classifier = PDRBPengeluaranClassifierLLM(
        supabase_client=supabase,
        embed_client=embed_client,
        llm_client=llm_client,
        llm_model=llm_model,
        top_k=7,
    )

    print(
        f"[Backfill PDRB Pengeluaran] Model: {llm_model} | "
        f"Workers: {args.workers} | Dry-run: {args.dry_run}"
    )

    all_articles = []
    offset = 0
    page_size = 1000
    while True:
        result = (
            supabase.table("berita")
            .select("id, title, content, kbli")
            .is_("pdrb_pengeluaran", "null")
            .order("id")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        rows = result.data or []
        all_articles.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size

    total = len(all_articles)
    if total == 0:
        print("[Backfill PDRB Pengeluaran] Tidak ada artikel yang perlu diproses.")
        return

    print(f"[Backfill PDRB Pengeluaran] Ditemukan {total} artikel - mulai proses...")
    print()

    t0 = time.time()
    texts = [_make_embed_text(article) for article in all_articles]
    embeddings = batch_embed_texts(texts, client=embed_client)
    embed_ok = sum(1 for item in embeddings if item is not None)
    print(
        f"[Backfill PDRB Pengeluaran] Embedding siap: {embed_ok}/{total} | "
        f"{time.time() - t0:.1f}s"
    )
    print()

    results: dict[int, str | None] = {}
    errors = 0
    done = 0
    t1 = time.time()

    def _classify_one(article: dict, embedding) -> tuple[int, str | None]:
        article_id = int(article["id"])
        title = (article.get("title") or "").strip()
        content = (article.get("content") or "").strip()
        kbli = article.get("kbli")

        if _is_kbli_irrelevant(kbli) or (not title and not content):
            return article_id, "—"
        if embedding is None:
            return article_id, None

        try:
            code = classifier.classify_with_embedding(content, title, embedding)
            if not code:
                return article_id, None
            return article_id, format_pdrb_pengeluaran_hasil(code)
        except Exception as exc:
            print(f"  [ERROR] ID={article_id}: {exc}")
            return article_id, None

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(_classify_one, article, embedding): int(article["id"])
            for article, embedding in zip(all_articles, embeddings)
        }
        for future in as_completed(futures):
            article_id = futures[future]
            try:
                result_id, label = future.result()
                results[result_id] = label
            except Exception:
                results[article_id] = None
                errors += 1
            done += 1
            if done % 50 == 0 or done == total:
                elapsed = time.time() - t1
                rate = done / elapsed if elapsed > 0 else 0
                print(f"  Progress: {done}/{total} ({rate:.1f}/s) | Errors: {errors}")

    classify_ok = sum(1 for value in results.values() if value is not None)
    print(
        f"[Backfill PDRB Pengeluaran] Klasifikasi selesai: {classify_ok}/{total} | "
        f"{time.time() - t1:.1f}s"
    )
    print()

    if args.dry_run:
        print("[Backfill PDRB Pengeluaran] DRY-RUN aktif - tidak ada perubahan DB.")
        for article_id, label in list(results.items())[:10]:
            print(f"  ID={article_id}: {label}")
        return

    ok = 0
    fail = 0
    items = list(results.items())
    for start in range(0, len(items), args.db_batch):
        chunk = items[start : start + args.db_batch]
        for article_id, label in chunk:
            if label is None:
                continue
            try:
                supabase.table("berita").update({"pdrb_pengeluaran": label}).eq("id", article_id).execute()
                ok += 1
            except Exception as exc:
                print(f"  [DB ERROR] ID={article_id}: {exc}")
                fail += 1
        print(f"  Update DB: {min(start + args.db_batch, len(items))}/{len(items)}")

    total_time = time.time() - t0
    print()
    print("=" * 60)
    print("[Backfill PDRB Pengeluaran] SELESAI")
    print(f"  Total artikel        : {total}")
    print(f"  Embedding berhasil   : {embed_ok}")
    print(f"  Klasifikasi berhasil : {classify_ok}")
    print(f"  DB update berhasil   : {ok}")
    print(f"  DB update gagal      : {fail}")
    print(f"  Total waktu          : {total_time:.0f}s ({total_time / 60:.1f} menit)")
    print("=" * 60)


if __name__ == "__main__":
    main()
