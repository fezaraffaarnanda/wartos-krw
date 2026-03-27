"""
Pipeline pemrosesan artikel: validasi, build row, insert ke DB,
backfill KBLI/Aktivitas/Embedding, serta worker thread scraping.
"""

import threading
import time as _time

from clients.supabase import supabase
from repositories.berita import _fetch_existing_urls
from repositories.scrape_log import _log_scrape_run
from state.scraping import (
    _scrape_progress,
    _scrape_overall,
    _scraping_lock,
)
from utils.date import normalize_date, parse_date_to_iso
from ai.embeddings import batch_embed_articles, embed_article, _build_embedding_client

from scrapers.radartegal import scrape_new_articles as scrape_radartegal
from scrapers.panturapost import scrape_new_articles as scrape_panturapost
from scrapers.tribunjateng import scrape_new_articles as scrape_tribunjateng
from scrapers.kompas import scrape_new_articles as scrape_kompas
from scrapers.setda_tegal import scrape_new_articles as scrape_tegal

# ── Konstanta ───────────────────────────────────────────────────────────────

SOURCE_LABELS = {
    "radartegal":   "Radar Tegal",
    "panturapost":  "Pantura Post",
    "tribunjateng": "Tribun Jateng",
    "kompas":       "Kompas",
    "setdategal":   "Setda Tegal",
}


# ── Lazy-loaded classifiers (diisi oleh app.py setelah init) ─────────────────
# Disimpan di dict agar bisa di-mutate dari app.py tanpa reassign.

_classifiers: dict = {
    "kbli_predictor":  None,
    "kbli_llm_client": None,
    "kbli_llm_model":  "",
    "pdrb_pengeluaran_predictor": None,
}


def set_classifiers(
    kbli_predictor,
    kbli_llm_client,
    kbli_llm_model: str,
    pdrb_pengeluaran_predictor=None,
) -> None:
    """Dipanggil oleh app.py setelah classifier berhasil diinisialisasi."""
    _classifiers["kbli_predictor"]  = kbli_predictor
    _classifiers["kbli_llm_client"] = kbli_llm_client
    _classifiers["kbli_llm_model"]  = kbli_llm_model
    _classifiers["pdrb_pengeluaran_predictor"] = pdrb_pengeluaran_predictor


# ── Validasi & klasifikasi artikel ──────────────────────────────────────────

def _is_valid_article(article: dict | None, source_key: str) -> bool:
    """Return False kalau artikel harus dilewati (null, judul kosong, atau field NA)."""
    if not article or not article.get("title") or not article.get("url"):
        print(f"[SKIP] {source_key}: artikel null/judul kosong dilewati")
        return False

    if source_key == "tribunjateng":
        for field in ("title", "date", "content"):
            val = article.get(field, "")
            if not val or str(val).strip().upper() == "NA":
                print(f"[SKIP] {source_key}: field '{field}' kosong/NA — {article.get('url', '')}")
                return False

    return True


def _is_kbli_irrelevant(kbli: str | None) -> bool:
    """Return True jika nilai KBLI menandakan artikel tidak relevan secara ekonomi."""
    if not kbli:
        return True
    return kbli.strip() in ("Tidak Relevan", "—")


def _build_article_row(article: dict, source_label: str) -> dict:
    """Rakit dict row siap insert ke tabel berita."""
    from ai.kbli import predict_kbli_label
    from ai.aktivitas import predict_aktivitas_label
    from ai.pdrb_pengeluaran import predict_pdrb_pengeluaran_label

    normalized_date = normalize_date(article["date"])
    kbli = predict_kbli_label(
        article.get("content"),
        _classifiers["kbli_predictor"],
        title=article.get("title"),
    )
    aktivitas = None
    pdrb_pengeluaran = None
    if not _is_kbli_irrelevant(kbli) and _classifiers["kbli_llm_client"] is not None:
        aktivitas = predict_aktivitas_label(
            article.get("content"),
            article.get("title"),
            _classifiers["kbli_llm_client"],
            _classifiers["kbli_llm_model"],
        )
    elif _is_kbli_irrelevant(kbli):
        aktivitas = "—"

    if not _is_kbli_irrelevant(kbli) and _classifiers["pdrb_pengeluaran_predictor"] is not None:
        pdrb_pengeluaran = predict_pdrb_pengeluaran_label(
            article.get("content"),
            _classifiers["pdrb_pengeluaran_predictor"],
            title=article.get("title"),
        )
    elif _is_kbli_irrelevant(kbli):
        pdrb_pengeluaran = "—"

    return {
        "title":             article["title"],
        "date":              normalized_date,
        "date_parsed":       parse_date_to_iso(normalized_date),
        "url":               article["url"],
        "content":           article["content"],
        "tags":              article["tags"].lower() if article.get("tags") else article.get("tags"),
        "kbli":              kbli,
        "aktivitas_ekonomi": aktivitas,
        "pdrb_pengeluaran":  pdrb_pengeluaran,
        "source":            article.get("source") or source_label,
    }


# ── Insert artikel ───────────────────────────────────────────────────────────

def _insert_articles(articles: list, source_key: str) -> int:
    """
    Insert artikel valid ke Supabase beserta embedding-nya.
    Embedding di-generate sebelum insert agar langsung tersimpan di row.
    Return jumlah yang berhasil diinsert.
    """
    source_label   = SOURCE_LABELS.get(source_key, source_key)
    inserted       = 0
    embedded_count = 0

    embed_client = None
    try:
        embed_client = _build_embedding_client()
    except Exception as exc:
        print(f"[Embedding] {source_key}: Gagal inisialisasi client — {exc}")

    for article in articles:
        if not _is_valid_article(article, source_key):
            continue
        try:
            row = _build_article_row(article, source_label)

            if embed_client is not None:
                try:
                    embedding = embed_article(row, client=embed_client)
                    if embedding:
                        row["embedding"] = embedding
                        embedded_count += 1
                except Exception as emb_exc:
                    print(f"[Embedding] {source_key}: Gagal embed '{row.get('url', '')}' — {emb_exc}")

            supabase.table("berita").insert(row).execute()
            inserted += 1
        except Exception as exc:
            print(f"[DB ERROR] {source_key}: {article.get('url', '')} — {exc}")

    _scrape_progress[source_key]["inserted"] = inserted
    print(f"[Embedding] {source_key}: {embedded_count}/{inserted} artikel baru di-embed saat insert.")
    return inserted


# ── Backfill KBLI ────────────────────────────────────────────────────────────

def _run_kbli_backfill(batch_size: int = 100) -> int:
    """
    Prediksi KBLI untuk semua berita yang kbli-nya NULL.
    Return jumlah artikel yang berhasil diupdate.
    """
    from ai.kbli import predict_kbli_label

    if _classifiers["kbli_predictor"] is None:
        print("[KBLI Backfill] Classifier tidak tersedia, backfill dilewati.")
        return 0

    total_updated = 0
    MAX_BATCHES   = 100
    iteration     = 0

    print("[KBLI Backfill] Mulai memproses artikel tanpa KBLI...")

    while iteration < MAX_BATCHES:
        iteration += 1

        try:
            result = (
                supabase.table("berita")
                .select("id, title, content")
                .is_("kbli", "null")
                .limit(batch_size)
                .execute()
            )
        except Exception as exc:
            print(f"[KBLI Backfill] Gagal query DB (batch {iteration}): {exc}")
            break

        rows = result.data or []
        if not rows:
            break

        updated_this_batch = 0

        for row in rows:
            content = (row.get("content") or "").strip()
            title   = (row.get("title")   or "").strip()

            label = predict_kbli_label(content, _classifiers["kbli_predictor"], title=title)

            if label is None:
                if not content and not title:
                    label = "—"
                else:
                    continue

            try:
                supabase.table("berita").update({"kbli": label}).eq("id", row["id"]).execute()
                updated_this_batch += 1
                total_updated += 1
            except Exception as exc:
                print(f"[KBLI Backfill] Gagal update id={row['id']}: {exc}")

        if updated_this_batch == 0:
            print(f"[KBLI Backfill] Batch {iteration} tidak ada update — menghentikan loop.")
            break

    print(f"[KBLI Backfill] Selesai. {total_updated} artikel diperbarui dalam {iteration} batch.")
    return total_updated


# ── Backfill Aktivitas Ekonomi ────────────────────────────────────────────────

def _run_aktivitas_backfill(batch_size: int = 50) -> int:
    """
    Prediksi Aktivitas Ekonomi untuk semua berita yang aktivitas_ekonomi IS NULL
    dan kbli IS NOT NULL.
    Return jumlah artikel yang berhasil diupdate.
    """
    from ai.aktivitas import predict_aktivitas_label

    if _classifiers["kbli_llm_client"] is None:
        print("[Aktivitas Backfill] LLM client tidak tersedia, backfill dilewati.")
        return 0

    total_updated = 0
    MAX_BATCHES   = 100
    iteration     = 0

    print("[Aktivitas Backfill] Mulai memproses artikel tanpa Aktivitas Ekonomi...")

    while iteration < MAX_BATCHES:
        iteration += 1

        try:
            result = (
                supabase.table("berita")
                .select("id, title, content, kbli")
                .is_("aktivitas_ekonomi", "null")
                .not_.is_("kbli", "null")
                .limit(batch_size)
                .execute()
            )
        except Exception as exc:
            print(f"[Aktivitas Backfill] Gagal query DB (batch {iteration}): {exc}")
            break

        rows = result.data or []
        if not rows:
            break

        updated_this_batch = 0

        for row in rows:
            kbli    = row.get("kbli") or ""
            content = (row.get("content") or "").strip()
            title   = (row.get("title")   or "").strip()

            if _is_kbli_irrelevant(kbli):
                label = "—"
            elif not content and not title:
                label = "—"
            else:
                label = predict_aktivitas_label(
                    content, title,
                    _classifiers["kbli_llm_client"],
                    _classifiers["kbli_llm_model"],
                )
                if label is None:
                    continue

            try:
                supabase.table("berita").update({"aktivitas_ekonomi": label}).eq("id", row["id"]).execute()
                updated_this_batch += 1
                total_updated += 1
            except Exception as exc:
                print(f"[Aktivitas Backfill] Gagal update id={row['id']}: {exc}")

        if updated_this_batch == 0:
            print(f"[Aktivitas Backfill] Batch {iteration} tidak ada update — menghentikan loop.")
            break

    print(f"[Aktivitas Backfill] Selesai. {total_updated} artikel diperbarui dalam {iteration} batch.")
    return total_updated


def _run_pdrb_pengeluaran_backfill(batch_size: int = 50) -> int:
    """
    Prediksi PDRB pengeluaran untuk semua berita yang pdrb_pengeluaran IS NULL.
    Return jumlah artikel yang berhasil diupdate.
    """
    from ai.pdrb_pengeluaran import predict_pdrb_pengeluaran_label

    if _classifiers["pdrb_pengeluaran_predictor"] is None:
        print("[PDRB Pengeluaran Backfill] Classifier tidak tersedia, backfill dilewati.")
        return 0

    total_updated = 0
    max_batches = 100
    iteration = 0

    print("[PDRB Pengeluaran Backfill] Mulai memproses artikel tanpa label PDRB pengeluaran...")

    while iteration < max_batches:
        iteration += 1

        try:
            result = (
                supabase.table("berita")
                .select("id, title, content, kbli")
                .is_("pdrb_pengeluaran", "null")
                .not_.is_("kbli", "null")
                .limit(batch_size)
                .execute()
            )
        except Exception as exc:
            print(f"[PDRB Pengeluaran Backfill] Gagal query DB (batch {iteration}): {exc}")
            break

        rows = result.data or []
        if not rows:
            break

        updated_this_batch = 0

        for row in rows:
            kbli = row.get("kbli") or ""
            content = (row.get("content") or "").strip()
            title = (row.get("title") or "").strip()

            if _is_kbli_irrelevant(kbli) or (not content and not title):
                label = "—"
            else:
                label = predict_pdrb_pengeluaran_label(
                    content,
                    _classifiers["pdrb_pengeluaran_predictor"],
                    title=title,
                )
                if label is None:
                    continue

            try:
                supabase.table("berita").update(
                    {"pdrb_pengeluaran": label}
                ).eq("id", row["id"]).execute()
                updated_this_batch += 1
                total_updated += 1
            except Exception as exc:
                print(f"[PDRB Pengeluaran Backfill] Gagal update id={row['id']}: {exc}")

        if updated_this_batch == 0:
            print(
                f"[PDRB Pengeluaran Backfill] Batch {iteration} tidak ada update - menghentikan loop."
            )
            break

    print(
        f"[PDRB Pengeluaran Backfill] Selesai. {total_updated} artikel diperbarui dalam {iteration} batch."
    )
    return total_updated


# ── Backfill Embedding ────────────────────────────────────────────────────────

def _run_embedding_backfill(batch_size: int = 20) -> int:
    """
    Backfill embedding untuk semua artikel yang embedding IS NULL.
    batch_size=20 → ~14.000 token/request, aman di bawah rate limit Gemini free tier.
    Delay 30 detik antar batch agar tidak melebihi 30k TPM.
    Return jumlah artikel yang berhasil di-embed.
    """
    _BACKFILL_SLEEP = 30

    try:
        embed_client = _build_embedding_client()
    except ValueError as exc:
        print(f"[Embedding Backfill] Tidak dapat inisialisasi client: {exc}")
        return 0

    total_embedded = 0
    MAX_BATCHES    = 200
    iteration      = 0

    print("[Embedding Backfill] Mulai memproses artikel tanpa embedding...")

    while iteration < MAX_BATCHES:
        iteration += 1

        try:
            result = (
                supabase.table("berita")
                .select("id, title, tags, content, kbli, date, date_parsed")
                .is_("embedding", "null")
                .order("id")
                .limit(batch_size)
                .execute()
            )
        except Exception as exc:
            print(f"[Embedding Backfill] Gagal query DB (batch {iteration}): {exc}")
            break

        rows = result.data or []
        if not rows:
            break

        ids = [r["id"] for r in rows]
        print(f"[Embedding Backfill] Batch {iteration}: {len(rows)} artikel (ID {ids[0]}–{ids[-1]})...")

        embeddings = batch_embed_articles(rows, client=embed_client)

        embedded_this_batch = 0
        for row, embedding in zip(rows, embeddings):
            if embedding is None:
                continue
            try:
                supabase.table("berita").update(
                    {"embedding": embedding}
                ).eq("id", row["id"]).execute()
                embedded_this_batch += 1
                total_embedded      += 1
            except Exception as exc:
                print(f"[Embedding Backfill] Gagal update id={row['id']}: {exc}")

        if embedded_this_batch == 0:
            print(f"[Embedding Backfill] Batch {iteration} tidak ada yang berhasil — menghentikan loop.")
            break

        _time.sleep(_BACKFILL_SLEEP)

    print(f"[Embedding Backfill] Selesai. {total_embedded} artikel di-embed dalam {iteration} batch.")
    return total_embedded


# ── Scraper config & runner ──────────────────────────────────────────────────

def _build_scraper_config(max_articles: int) -> list[tuple]:
    """Return daftar (key, scraper_fn, kwargs) untuk semua sumber."""
    max_pages = max(1, max_articles // 30)
    return [
        ("radartegal",   scrape_radartegal,   {"max_pages": max_pages}),
        ("panturapost",  scrape_panturapost,  {"max_articles": max_articles}),
        ("tribunjateng", scrape_tribunjateng, {"max_articles": max_articles}),
        ("kompas",       scrape_kompas,       {"max_articles": max_articles}),
        ("setdategal",   scrape_tegal,        {"max_articles": max_articles}),
    ]


def _make_progress_callback(source_key: str):
    """Factory: buat callback progress untuk satu sumber berita."""
    def on_progress(count, msg=""):
        _scrape_progress[source_key]["scraped"] = count
        _scrape_progress[source_key]["message"] = msg or f"{count} berita ditemukan"
    return on_progress


def _run_scraper_source(
    key: str,
    scraper_fn,
    existing_urls: set,
    kwargs: dict,
) -> int:
    """Jalankan satu sumber scraper, update progress, dan insert hasilnya."""
    _scrape_progress[key]["status"]  = "running"
    _scrape_progress[key]["message"] = "Memulai scraping..."

    articles = scraper_fn(existing_urls, on_progress=_make_progress_callback(key), **kwargs)
    n = _insert_articles(articles, key)

    _scrape_progress[key]["status"]  = "done"
    _scrape_progress[key]["message"] = f"Selesai — {n} berita disimpan"
    print(f"[SCRAPE] {key}: {n} disimpan")
    return n


# ── Worker thread (background scraping) ─────────────────────────────────────

def _scrape_worker(max_articles: int) -> None:
    try:
        existing_urls = _fetch_existing_urls()
        print(f"[SCRAPE] {len(existing_urls)} URL sudah ada di database.")

        total_inserted = sum(
            _run_scraper_source(key, fn, existing_urls, kwargs)
            for key, fn, kwargs in _build_scraper_config(max_articles)
        )

        _scrape_overall["total_inserted"] = total_inserted
        _log_scrape_run(total_inserted)
        print(f"[SCRAPE] Semua selesai. Total {total_inserted} berita baru disimpan.")

        if _classifiers["kbli_predictor"] is not None:
            threading.Thread(
                target=_run_kbli_backfill,
                daemon=True,
                name="kbli-backfill-post-scrape",
            ).start()

        threading.Thread(
            target=_run_embedding_backfill,
            daemon=True,
            name="embedding-backfill-post-scrape",
        ).start()

        if _classifiers["kbli_llm_client"] is not None:
            threading.Thread(
                target=_run_aktivitas_backfill,
                daemon=True,
                name="aktivitas-backfill-post-scrape",
            ).start()

    except Exception as exc:
        _scrape_overall["error"] = str(exc)
        print(f"[SCRAPE ERROR] {exc}")
        for key in _scrape_progress:
            if _scrape_progress[key]["status"] == "running":
                _scrape_progress[key].update({"status": "error", "message": f"Error: {exc}"})

    finally:
        _scrape_overall["active"] = False
        _scrape_overall["done"]   = True
        _scraping_lock.release()


# ── Synchronous scrape (untuk cron / Vercel serverless) ─────────────────────

def _scrape_sync(max_articles: int) -> dict:
    """Jalankan scraping secara synchronous. Cocok untuk Vercel serverless."""
    results        = {}
    total_inserted = 0
    errors         = []

    try:
        existing_urls = _fetch_existing_urls()
        print(f"[SCRAPE-SYNC] {len(existing_urls)} URL sudah ada di database.")
    except Exception as exc:
        return {"status": "error", "message": f"Gagal fetch existing URLs: {exc}"}

    for key, scraper_fn, kwargs in _build_scraper_config(max_articles):
        try:
            articles       = scraper_fn(existing_urls, **kwargs)
            n              = _insert_articles(articles, key)
            results[key]   = n
            total_inserted += n
            print(f"[SCRAPE-SYNC] {key}: {n} disimpan")
        except Exception as exc:
            errors.append(f"{key}: {exc}")
            print(f"[SCRAPE-SYNC ERROR] {key}: {exc}")

    print(f"[SCRAPE-SYNC] Selesai. Total {total_inserted} berita baru disimpan.")
    _log_scrape_run(total_inserted)

    if _classifiers["kbli_predictor"] is not None:
        try:
            _run_kbli_backfill()
        except Exception as exc:
            print(f"[SCRAPE-SYNC] KBLI backfill error: {exc}")

    try:
        _run_embedding_backfill()
    except Exception as exc:
        print(f"[SCRAPE-SYNC] Embedding backfill error: {exc}")

    if _classifiers["kbli_llm_client"] is not None:
        try:
            _run_aktivitas_backfill()
        except Exception as exc:
            print(f"[SCRAPE-SYNC] Aktivitas backfill error: {exc}")

    return {
        "status":         "ok",
        "total_inserted": total_inserted,
        "results":        results,
        "errors":         errors,
    }
