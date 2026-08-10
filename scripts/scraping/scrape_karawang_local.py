"""
Scraping massal dari lokal langsung ke Supabase (tanpa Flask berjalan).

Menginisialisasi classifier (relevance + KBLI + PDRB + embedding) persis seperti
app.py, lalu menjalankan pipeline scraping secara synchronous untuk 4 kanal Karawang.

Pemakaian:
    python -m scripts.scraping.scrape_karawang_local
    python -m scripts.scraping.scrape_karawang_local --max 500
    python -m scripts.scraping.scrape_karawang_local --source radar_karawang --max 300

Catatan:
    - Butuh GEMINI_API_KEY + kredensial Supabase di .env.
    - Insert, gerbang relevance, klasifikasi KBLI/PDRB, dan embedding ikut jalan
      seperti pada scraping via web.
"""

from __future__ import annotations

import argparse

from dotenv import load_dotenv


def _init_classifiers():
    """Inisialisasi & daftarkan classifier ke article_pipeline (mirror app.py)."""
    from clients.supabase import supabase
    from clients.llm import build_chat_client
    from ai.embeddings import _build_embedding_client
    from ai.kbli import load_kbli_llm_classifier
    from ai.pdrb_pengeluaran import load_pdrb_pengeluaran_llm_classifier
    from services.article_pipeline import set_classifiers

    embed_client = None
    try:
        embed_client = _build_embedding_client()
    except Exception as exc:
        print(f"[INIT] Gagal buat embedding client: {exc}")

    llm_client, llm_model = None, ""
    try:
        llm_client, llm_model = build_chat_client()
    except Exception as exc:
        print(f"[INIT] Gagal buat LLM client: {exc}")

    kbli_predictor = load_kbli_llm_classifier(supabase, embed_client, llm_client, llm_model)
    pdrb_predictor = load_pdrb_pengeluaran_llm_classifier(supabase, embed_client, llm_client, llm_model)

    set_classifiers(
        kbli_predictor,
        llm_client,
        llm_model,
        pdrb_predictor,
        relevance_llm_client=llm_client,
        relevance_llm_model=llm_model,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scraping massal Karawang ke Supabase (lokal)")
    parser.add_argument("--max", type=int, default=300, help="Maks berita per source (default: 300)")
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Scrape satu kanal saja: inews_karawang | karawangnews | pemda_karawang | radar_karawang",
    )
    return parser


def main() -> int:
    load_dotenv()
    args = _build_parser().parse_args()
    max_articles = max(1, min(int(args.max), 9999))

    _init_classifiers()

    from repositories.berita import _fetch_existing_urls
    from services.article_pipeline import (
        _build_scraper_config,
        _insert_articles,
        _run_relevance_backfill,
        _run_kbli_backfill,
        _run_embedding_backfill,
        _classifiers,
    )

    config = _build_scraper_config(max_articles)
    if args.source:
        config = [c for c in config if c[0] == args.source]
        if not config:
            print(f"ERROR: source '{args.source}' tidak dikenal.")
            return 1

    existing_urls = _fetch_existing_urls()
    print(f"[LOCAL SCRAPE] {len(existing_urls)} URL sudah ada di database.")

    total = 0
    for key, scraper_fn, kwargs in config:
        try:
            articles = scraper_fn(existing_urls, **kwargs)
            n = _insert_articles(articles, key)
            total += n
            print(f"[LOCAL SCRAPE] {key}: {n} disimpan")
        except Exception as exc:
            print(f"[LOCAL SCRAPE ERROR] {key}: {exc}")

    print(f"[LOCAL SCRAPE] Total {total} berita baru disimpan. Menjalankan backfill...")

    if _classifiers["relevance_llm_client"] is not None:
        _run_relevance_backfill()
    if _classifiers["kbli_predictor"] is not None:
        _run_kbli_backfill()
    _run_embedding_backfill()

    print("[LOCAL SCRAPE] Selesai.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
