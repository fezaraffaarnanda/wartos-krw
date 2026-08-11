"""
Pipeline pemrosesan artikel: validasi, build row, insert ke DB,
backfill KBLI/Aktivitas/Embedding, serta worker thread scraping.
"""

import threading
import time as _time
from datetime import datetime, timezone

from clients.supabase import supabase
from config.region import SOURCE_LABELS  # noqa: F401  (re-export, dipakai luas)
from repositories.berita import _fetch_existing_urls
from repositories.scrape_log import _log_scrape_run
from state.scraping import (
    _scrape_progress,
    _scrape_overall,
    _scraping_lock,
)
from utils.date import normalize_date, parse_date_to_iso
from utils.tags import clean_tags
from ai.embeddings import batch_embed_articles, embed_article, _build_embedding_client

from scrapers.inews_karawang import scrape_new_articles as scrape_inews_karawang
from scrapers.karawangnews import scrape_new_articles as scrape_karawangnews
from scrapers.pemda_karawang import scrape_new_articles as scrape_pemda_karawang
from scrapers.radar_karawang import scrape_new_articles as scrape_radar_karawang


# ── Lazy-loaded classifiers (diisi oleh app.py setelah init) ─────────────────
# Disimpan di dict agar bisa di-mutate dari app.py tanpa reassign.

_classifiers: dict = {
    "kbli_predictor":  None,
    "kbli_llm_client": None,
    "kbli_llm_model":  "",
    "pdrb_pengeluaran_predictor": None,
    "relevance_llm_client": None,
    "relevance_llm_model":  "",
}


def set_classifiers(
    kbli_predictor,
    kbli_llm_client,
    kbli_llm_model: str,
    pdrb_pengeluaran_predictor=None,
    relevance_llm_client=None,
    relevance_llm_model: str = "",
) -> None:
    """Dipanggil oleh app.py setelah classifier berhasil diinisialisasi."""
    _classifiers["kbli_predictor"]  = kbli_predictor
    _classifiers["kbli_llm_client"] = kbli_llm_client
    _classifiers["kbli_llm_model"]  = kbli_llm_model
    _classifiers["pdrb_pengeluaran_predictor"] = pdrb_pengeluaran_predictor
    _classifiers["relevance_llm_client"] = relevance_llm_client
    _classifiers["relevance_llm_model"]  = relevance_llm_model


# ── Validasi & klasifikasi artikel ──────────────────────────────────────────

def _is_valid_article(article: dict | None, source_key: str) -> bool:
    """Return False kalau artikel harus dilewati (null, judul kosong, atau field NA)."""
    if not article or not article.get("title") or not article.get("url"):
        print(f"[SKIP] {source_key}: artikel null/judul kosong dilewati")
        return False

    return True


def _is_kbli_irrelevant(kbli: str | None) -> bool:
    """Return True jika nilai KBLI menandakan artikel tidak relevan secara ekonomi."""
    if not kbli:
        return True
    return kbli.strip() in ("Tidak Relevan", "—")


def _classify_relevance_for_article(article: dict) -> dict:
    """
    Jalankan classifier tahap-1. Return dict field relevance siap masuk row,
    plus dua flag kontrol:
      checked   : True hanya kalau classifier BERHASIL menghasilkan skor —
                  dipakai set relevance_checked_at (watermark klasifikasi).
      attempted : True kalau LLM benar-benar dipanggil — dipakai naikkan
                  relevance_attempts. Beda dengan checked karena panggilan
                  yang gagal tetap "dicoba", client None berarti belum sempat.
    Fallback aman: jika classifier tidak tersedia / gagal → anggap relevan
    (jangan buang data diam-diam), skor None.
    """
    from ai.relevance import classify_relevance

    client = _classifiers["relevance_llm_client"]
    model  = _classifiers["relevance_llm_model"]

    if client is None:
        # Classifier belum siap (mis. startup) -- BUKAN percobaan gagal, jadi
        # attempts tidak naik dan backfill akan mencoba lagi begitu classifier ada.
        return {
            "is_relevant":      True,
            "relevance_score":  None,
            "relevance_reason": None,
            "classifier_model": None,
            "prompt_version":   None,
            "checked":          False,
            "attempted":        False,
        }

    result = classify_relevance(
        article.get("content"),
        article.get("title"),
        client,
        model,
    )
    if result is None:
        # Gagal klasifikasi — fallback konservatif: tetap proses sebagai relevan.
        # attempted=True (LLM benar-benar dipanggil) sehingga relevance_attempts
        # naik dan backfill berhenti retry setelah max_attempts.
        return {
            "is_relevant":      True,
            "relevance_score":  None,
            "relevance_reason": "Classifier relevance gagal/menghasilkan output tak valid — fallback dianggap relevan.",
            "classifier_model": None,
            "prompt_version":   None,
            "checked":          False,
            "attempted":        True,
        }

    return {
        "is_relevant":      result["is_relevant"],
        "relevance_score":  result["score"],
        "relevance_reason": result["reason"],
        "classifier_model": result["classifier_model"],
        "prompt_version":   result["prompt_version"],
        "checked":          True,
        "attempted":        True,
    }


def _build_article_row(article: dict, source_label: str) -> dict:
    """Rakit dict row siap insert ke tabel berita."""
    from ai.kbli import predict_kbli_label
    from ai.aktivitas import predict_aktivitas_label
    from ai.pdrb_pengeluaran import predict_pdrb_pengeluaran_label

    normalized_date = normalize_date(article["date"])
    clean_tags_value = clean_tags(article.get("tags")).lower() or None

    # ── Gerbang tahap-1: relevance ────────────────────────────────────────────
    rel = _classify_relevance_for_article(article)
    relevance_fields = {
        "is_relevant":              rel["is_relevant"],
        "relevance_score":          rel["relevance_score"],
        "relevance_reason":         rel["relevance_reason"],
        "classifier_model":         rel["classifier_model"],
        "relevance_prompt_version": rel["prompt_version"],
        "relevance_attempts":       1 if rel["attempted"] else 0,
    }
    if rel["checked"]:
        relevance_fields["relevance_checked_at"] = datetime.now(timezone.utc).isoformat()

    if not rel["is_relevant"]:
        # Tidak relevan secara ekonomi → lewati classifier mahal (hemat cost).
        return {
            "title":             article["title"],
            "date":              normalized_date,
            "date_parsed":       parse_date_to_iso(normalized_date),
            "url":               article["url"],
            "content":           article["content"],
            "tags":              clean_tags_value,
            "kbli":              "—",
            "aktivitas_ekonomi": "—",
            "pdrb_pengeluaran":  "—",
            "source":            article.get("source") or source_label,
            **relevance_fields,
        }

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
        "tags":              clean_tags_value,
        "kbli":              kbli,
        "aktivitas_ekonomi": aktivitas,
        "pdrb_pengeluaran":  pdrb_pengeluaran,
        "source":            article.get("source") or source_label,
        **relevance_fields,
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


# ── Backfill Relevance (gerbang tahap-1) ─────────────────────────────────────

def _apply_reclassify_result(
    berita_repo, berita_id: int, *, content: str, title: str, attempts: int,
) -> dict | None:
    """Panggil classifier untuk satu baris dan simpan hasilnya.

    Dipakai bersama oleh backfill dan reclassify_article() manual supaya
    keduanya tidak bisa diam-diam berbeda perilaku.
    Return dict hasil classify_relevance kalau BERHASIL, None kalau gagal
    (attempts tetap dinaikkan lewat mark_relevance_attempt_failed).
    """
    from ai.relevance import classify_relevance

    client = _classifiers["relevance_llm_client"]
    model  = _classifiers["relevance_llm_model"]

    res = classify_relevance(content, title, client, model)
    if res is None:
        berita_repo.mark_relevance_attempt_failed(berita_id, attempts=attempts)
        return None

    ok = berita_repo.apply_relevance_result(
        berita_id,
        score=res["score"],
        is_relevant=res["is_relevant"],
        reason=res["reason"],
        classifier_model=res["classifier_model"],
        prompt_version=res["prompt_version"],
        attempts=attempts,
    )
    if not ok:
        return None

    if not res["is_relevant"]:
        # Konsisten dengan insert-time: lewati klasifikasi KBLI/aktivitas/PDRB mahal.
        try:
            supabase.table("berita").update({
                "kbli": "—", "aktivitas_ekonomi": "—", "pdrb_pengeluaran": "—",
            }).eq("id", berita_id).execute()
        except Exception as exc:
            print(f"[Relevance] Gagal set placeholder KBLI id={berita_id}: {exc}")

    return res


def _run_relevance_backfill(batch_size: int = 50, *, max_attempts: int = 3) -> int:
    """
    Prediksi relevance untuk semua berita yang BELUM PERNAH berhasil
    diklasifikasi (relevance_checked_at IS NULL) -- predikat baru yang
    menggantikan `is_relevant IS NULL` lama. Predikat lama tidak pernah
    menjaring baris fail-open karena baris itu ditandai is_relevant=True
    tanpa skor saat gagal, bukan NULL.

    Untuk artikel tidak relevan, langsung set kbli/aktivitas/pdrb = "—" agar
    backfill mahal melewatinya. Untuk artikel relevan, biarkan kbli NULL
    supaya diproses backfill KBLI. Baris yang gagal max_attempts kali
    berhenti di-retry otomatis -- tetap terlihat di tab "Gagal Diklasifikasi"
    untuk re-classify manual dari UI (yang mengabaikan batas ini).
    Return jumlah artikel yang berhasil diupdate.
    """
    from repositories.berita import BeritaRepository

    client = _classifiers["relevance_llm_client"]
    if client is None:
        print("[Relevance Backfill] Classifier tidak tersedia, backfill dilewati.")
        return 0

    berita_repo = BeritaRepository()
    total_updated = 0
    MAX_BATCHES   = 200
    iteration     = 0

    print("[Relevance Backfill] Mulai memproses artikel yang belum pernah berhasil diklasifikasi...")

    while iteration < MAX_BATCHES:
        iteration += 1

        try:
            rows = berita_repo.list_unchecked_relevance_rows(limit=batch_size, max_attempts=max_attempts)
        except Exception as exc:
            print(f"[Relevance Backfill] Gagal query DB (batch {iteration}): {exc}")
            break

        if not rows:
            break

        updated_this_batch = 0

        for row in rows:
            content  = (row.get("content") or "").strip()
            title    = (row.get("title")   or "").strip()
            attempts = int(row.get("relevance_attempts") or 0) + 1

            res = _apply_reclassify_result(
                berita_repo, row["id"], content=content, title=title, attempts=attempts,
            )
            if res is not None:
                updated_this_batch += 1
                total_updated += 1

        if updated_this_batch == 0:
            print(f"[Relevance Backfill] Batch {iteration} tidak ada update berhasil — menghentikan loop.")
            break

    print(f"[Relevance Backfill] Selesai. {total_updated} artikel diperbarui dalam {iteration} batch.")
    return total_updated


def reclassify_article(berita_id: int) -> dict | None:
    """Klasifikasi ulang satu artikel secara manual (dipanggil endpoint admin).

    Mengabaikan batas relevance_attempts backfill -- ini permintaan eksplisit
    dari admin, bukan retry otomatis. Return dict hasil atau None kalau
    classifier tidak tersedia / artikel tidak ditemukan / klasifikasi gagal.
    """
    from repositories.berita import BeritaRepository

    if _classifiers["relevance_llm_client"] is None:
        return None

    berita_repo = BeritaRepository()
    row = berita_repo.get_relevance_item(berita_id)
    if not row:
        return None

    content  = (row.get("content") or "").strip()
    title    = (row.get("title")   or "").strip()
    attempts = int(row.get("relevance_attempts") or 0) + 1

    res = _apply_reclassify_result(
        berita_repo, berita_id, content=content, title=title, attempts=attempts,
    )
    if res is None:
        return None

    return {
        "id":                       berita_id,
        "relevance_score":          res["score"],
        "is_relevant":              res["is_relevant"],
        "relevance_reason":         res["reason"],
        "classifier_model":         res["classifier_model"],
        "relevance_prompt_version": res["prompt_version"],
    }


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

_SCRAPER_FUNCS = {
    "inews_karawang": scrape_inews_karawang,
    "karawangnews":   scrape_karawangnews,
    "pemda_karawang": scrape_pemda_karawang,
    "radar_karawang": scrape_radar_karawang,
}


def _build_scraper_config(max_articles: int, backfill: bool = False) -> list[tuple]:
    """Return daftar (key, scraper_fn, kwargs) untuk semua sumber di SOURCE_LABELS.

    Registry-driven: sumber terdaftar di config.region.NEWS_SOURCES tapi
    tanpa fungsi scraper di _SCRAPER_FUNCS akan gagal saat scraping dipicu,
    bukan diam-diam dilewati.

    backfill=True: scraper skip duplikat alih-alih berhenti total, dipakai
    untuk isi database dari berita lama beberapa bulan ke belakang.
    """
    missing = set(SOURCE_LABELS) - set(_SCRAPER_FUNCS)
    if missing:
        raise RuntimeError(
            f"Sumber terdaftar di config.region.NEWS_SOURCES tapi tidak punya "
            f"scraper: {sorted(missing)}"
        )
    return [
        (key, _SCRAPER_FUNCS[key], {"max_articles": max_articles, "backfill": backfill})
        for key in SOURCE_LABELS
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

def _scrape_worker(max_articles: int, backfill: bool = False) -> None:
    try:
        existing_urls = _fetch_existing_urls()
        print(f"[SCRAPE] {len(existing_urls)} URL sudah ada di database.")
        if backfill:
            print("[SCRAPE] Mode backfill aktif — duplikat di-skip, bukan berhenti.")

        total_inserted = sum(
            _run_scraper_source(key, fn, existing_urls, kwargs)
            for key, fn, kwargs in _build_scraper_config(max_articles, backfill)
        )

        _scrape_overall["total_inserted"] = total_inserted
        _log_scrape_run(total_inserted)
        print(f"[SCRAPE] Semua selesai. Total {total_inserted} berita baru disimpan.")

        # Gerbang relevance → KBLI berjalan setelahnya dalam thread yang sama
        # agar artikel tidak-relevan sudah ditandai "—" sebelum backfill KBLI.
        def _relevance_then_kbli_backfill():
            if _classifiers["relevance_llm_client"] is not None:
                _run_relevance_backfill()
            if _classifiers["kbli_predictor"] is not None:
                _run_kbli_backfill()

        threading.Thread(
            target=_relevance_then_kbli_backfill,
            daemon=True,
            name="relevance-kbli-backfill-post-scrape",
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

def _scrape_sync(max_articles: int, backfill: bool = False) -> dict:
    """Jalankan scraping secara synchronous. Cocok untuk Vercel serverless."""
    results        = {}
    total_inserted = 0
    errors         = []

    try:
        existing_urls = _fetch_existing_urls()
        print(f"[SCRAPE-SYNC] {len(existing_urls)} URL sudah ada di database.")
        if backfill:
            print("[SCRAPE-SYNC] Mode backfill aktif — duplikat di-skip, bukan berhenti.")
    except Exception as exc:
        return {"status": "error", "message": f"Gagal fetch existing URLs: {exc}"}

    for key, scraper_fn, kwargs in _build_scraper_config(max_articles, backfill):
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

    if _classifiers["relevance_llm_client"] is not None:
        try:
            _run_relevance_backfill()
        except Exception as exc:
            print(f"[SCRAPE-SYNC] Relevance backfill error: {exc}")

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
