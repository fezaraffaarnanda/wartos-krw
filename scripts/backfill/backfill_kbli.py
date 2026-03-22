"""
scripts.backfill.backfill_kbli — Backfill kolom KBLI (versi batch, optimized untuk RPM tinggi).

Strategi:
  1. Fetch SEMUA artikel NULL kbli dari DB sekaligus
  2. Batch embed semua teks (100 artikel per API call Gemini)
  3. Untuk setiap artikel: RPC match_kbli + LLM classify (paralel via ThreadPoolExecutor)
  4. Bulk update DB per batch

Hasil: 754 artikel bisa selesai dalam < 5 menit dengan 4k RPM.

Pemakaian:
    python -m scripts.backfill.backfill_kbli                   # semua NULL
    python -m scripts.backfill.backfill_kbli --workers 20      # jumlah thread paralel LLM
    python -m scripts.backfill.backfill_kbli --dry-run         # preview tanpa update DB
"""

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
from supabase import create_client

from ai.embeddings import _build_embedding_client, batch_embed_texts
from ai.kbli import format_kbli_hasil
from ai.kbli_classifier import (
    KBLIClassifierLLM,
    _MAX_ARTICLE_CHARS,
    _MAX_DESKRIPSI_CHARS,
    _SPECIAL_CODES,
    _SYSTEM_PROMPT,
    _USER_PROMPT,
    _VALID_KBLI_CODES,
)
from clients.llm import build_chat_client

load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="Batch backfill KBLI dengan LLM paralel.")
    parser.add_argument("--workers",  type=int,  default=15,    help="Thread paralel untuk LLM (default: 15)")
    parser.add_argument("--db-batch", type=int,  default=50,    help="Jumlah update DB per batch (default: 50)")
    parser.add_argument("--dry-run",  action="store_true",      help="Preview tanpa update DB")
    args = parser.parse_args()

    # ── Inisialisasi ──────────────────────────────────────────────────────────
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

    classifier = KBLIClassifierLLM(supabase, embed_client, llm_client, llm_model, top_k=5)
    print(f"[Backfill] Model: {llm_model} | Workers: {args.workers} | Dry-run: {args.dry_run}")

    # ── Step 1: Fetch semua artikel NULL kbli ─────────────────────────────────
    print("[Backfill] Mengambil semua artikel dengan KBLI NULL...")
    all_articles = []
    offset = 0
    PAGE = 1000
    while True:
        res = (
            supabase.table("berita")
            .select("id, title, content")
            .is_("kbli", "null")
            .order("id")
            .range(offset, offset + PAGE - 1)
            .execute()
        )
        batch = res.data or []
        all_articles.extend(batch)
        if len(batch) < PAGE:
            break
        offset += PAGE

    total = len(all_articles)
    if total == 0:
        print("[Backfill] Tidak ada artikel dengan KBLI NULL.")
        return

    print(f"[Backfill] Ditemukan {total} artikel — mulai proses...")
    print()

    # ── Step 2: Batch embed semua teks sekaligus ──────────────────────────────
    print(f"[Backfill] Step 1/3: Batch embedding {total} artikel...")
    t0 = time.time()

    # Buat teks embedding per artikel (gabungan title + content)
    def _make_embed_text(a: dict) -> str:
        title   = (a.get("title")   or "").strip()
        content = (a.get("content") or "").strip()
        parts = []
        if title:   parts.append(f"Judul: {title}")
        if content: parts.append(f"Konten: {content[:2000]}")
        return "\n".join(parts)

    texts = [_make_embed_text(a) for a in all_articles]
    embeddings = batch_embed_texts(texts, client=embed_client)   # list[list[float] | None]

    embed_ok   = sum(1 for e in embeddings if e is not None)
    embed_fail = total - embed_ok
    print(f"[Backfill]   -> {embed_ok}/{total} embedding berhasil ({embed_fail} gagal) | {time.time()-t0:.1f}s")
    print()

    # ── Step 3: Paralel classify via LLM ─────────────────────────────────────
    print(f"[Backfill] Step 2/3: Klasifikasi LLM paralel ({args.workers} thread)...")
    t1 = time.time()

    # Pasangkan artikel dengan embedding-nya
    tasks = []
    for article, emb in zip(all_articles, embeddings):
        tasks.append((article, emb))

    results: dict[int, str] = {}   # article_id → label
    done = 0
    errors = 0

    def _classify_one(article: dict, embedding) -> tuple[int, str | None]:
        """Classify satu artikel: RPC match_kbli + LLM, return (id, label)."""
        art_id  = article["id"]
        content = (article.get("content") or "").strip()
        title   = (article.get("title")   or "").strip()

        if not content and not title:
            return art_id, "—"

        try:
            # Gunakan pre-computed embedding jika tersedia, fallback ke classify normal
            if embedding is not None:
                # Ambil top-K kandidat langsung dengan embedding yang sudah ada
                try:
                    rpc_res = supabase.rpc(
                        "match_kbli",
                        {"query_embedding": embedding, "top_k": 5},
                    ).execute()
                    candidates = rpc_res.data or []
                except Exception:
                    candidates = []

                # Build prompt manual (sama dengan _build_prompt di KBLIClassifierLLM)
                kandidat_lines = []
                for c in candidates:
                    kode  = c.get("kode", "?")
                    judul = c.get("judul", "")
                    deskr = (c.get("deskripsi") or "")[:_MAX_DESKRIPSI_CHARS]
                    kandidat_lines.append(f"[{kode}] {judul} — {deskr}")

                kandidat_block = "\n".join(kandidat_lines) if kandidat_lines else "(Tidak ada kandidat)"
                valid_codes_str = ", ".join(sorted(_VALID_KBLI_CODES)) + ", Tidak Relevan"

                system = _SYSTEM_PROMPT.format(
                    kandidat_block=kandidat_block,
                    ke_deskripsi=_SPECIAL_CODES["KE"]["deskripsi"],
                    pg_deskripsi=_SPECIAL_CODES["PG"]["deskripsi"],
                    valid_codes=valid_codes_str,
                )
                isi = content[:_MAX_ARTICLE_CHARS] + ("..." if len(content) > _MAX_ARTICLE_CHARS else "")
                user_msg = _USER_PROMPT.format(
                    judul=title or "(tanpa judul)",
                    isi=isi or title,
                )
                prompt = system + "\n" + user_msg

                raw = classifier._call_llm(prompt)
                label_code = classifier._parse_response(raw)
            else:
                # Fallback: pakai classify normal (akan embed ulang)
                label_code = classifier.classify(content, title=title)

            if not label_code:
                return art_id, None

            # Format ke "KODE/Deskripsi"
            from ai.kbli import format_kbli_hasil
            return art_id, format_kbli_hasil(label_code)

        except Exception as exc:
            print(f"  [ERROR] ID={art_id}: {exc}")
            return art_id, None

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_classify_one, a, e): a["id"] for a, e in tasks}
        for fut in as_completed(futures):
            art_id = futures[fut]
            try:
                aid, label = fut.result()
                results[aid] = label
            except Exception as exc:
                results[art_id] = None
                errors += 1
            done += 1
            if done % 50 == 0 or done == total:
                elapsed = time.time() - t1
                rate = done / elapsed if elapsed > 0 else 0
                print(f"  Progress: {done}/{total} ({rate:.1f}/s) | Errors: {errors}")

    classify_ok   = sum(1 for v in results.values() if v is not None)
    classify_fail = total - classify_ok
    print(f"[Backfill]   -> {classify_ok}/{total} berhasil diklasifikasi | {time.time()-t1:.1f}s")
    print()

    # ── Step 4: Bulk update DB ────────────────────────────────────────────────
    if args.dry_run:
        print("[Backfill] DRY-RUN aktif — tidak ada perubahan ke DB.")
        sample = list(results.items())[:10]
        for aid, lbl in sample:
            print(f"  ID={aid}: {lbl}")
        return

    print(f"[Backfill] Step 3/3: Update DB ({len(results)} artikel)...")
    t2   = time.time()
    ok   = 0
    fail = 0

    items = list(results.items())
    for i in range(0, len(items), args.db_batch):
        chunk = items[i : i + args.db_batch]
        for art_id, label in chunk:
            if label is None:
                continue
            try:
                supabase.table("berita").update({"kbli": label}).eq("id", art_id).execute()
                ok += 1
            except Exception as exc:
                print(f"  [DB ERROR] ID={art_id}: {exc}")
                fail += 1
        print(f"  Update DB: {min(i + args.db_batch, len(items))}/{len(items)}")

    total_time = time.time() - t0
    print()
    print("=" * 60)
    print("[Backfill] SELESAI")
    print(f"  Total artikel        : {total}")
    print(f"  Embedding berhasil   : {embed_ok}")
    print(f"  Klasifikasi berhasil : {classify_ok}")
    print(f"  DB update berhasil   : {ok}")
    print(f"  DB update gagal      : {fail}")
    print(f"  Total waktu          : {total_time:.0f}s ({total_time/60:.1f} menit)")
    print("=" * 60)


if __name__ == "__main__":
    main()
