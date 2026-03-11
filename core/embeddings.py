"""
embeddings.py — Modul Vector Embedding untuk RAG

Mengelola pembuatan embedding artikel menggunakan Google gemini-embedding-001
via Gemini OpenAI-compatible endpoint (GEMINI_API_KEY), dan semantic search
via Supabase pgvector (RPC match_articles).

Catatan arsitektur:
- Embedding  → Google Gemini API (modul ini, GEMINI_API_KEY)
- AI Insights → Gemini / DeepSeek fallback (core/ai_insights.py)
- RAG Chat   → Gemini / DeepSeek fallback (core/rag_chat.py)
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI

# ── Konstanta ──────────────────────────────────────────────────────────────────

_EMBEDDING_MODEL     = "gemini-embedding-001"
_EMBEDDING_DIMS      = 1536   # Gemini mendukung 3072/1536/768 — pakai 1536 agar kompatibel dgn skema DB

# Gemini OpenAI-compatible endpoint untuk embeddings
_GEMINI_EMBED_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

# Panjang konten artikel yang dipakai untuk embedding (lebih panjang = representasi lebih kaya)
_EMBED_CONTENT_CHARS = 2000

# Batch size untuk API call
_BATCH_SIZE = 100

# Jeda antar batch (detik)
_BATCH_SLEEP = 0.3


# ── Client builder ─────────────────────────────────────────────────────────────

def _build_embedding_client() -> OpenAI:
    """Buat client ke Google Gemini embedding API menggunakan GEMINI_API_KEY."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY tidak ditemukan di environment variables.")
    return OpenAI(api_key=api_key, base_url=_GEMINI_EMBED_BASE_URL)


# ── Teks preparation ───────────────────────────────────────────────────────────

def _prepare_text(article: dict) -> str:
    """
    Gabungkan tanggal, KBLI, judul, tags, dan konten artikel menjadi satu teks untuk di-embed.
    Format terstruktur membantu model memahami konteks setiap field.

    Field yang digunakan (jika tersedia):
    - date_parsed : tanggal ISO (YYYY-MM-DD), lebih bersih untuk sorting/filter semantik
    - date        : fallback jika date_parsed kosong
    - kbli        : kategori sektor KBLI, memperkaya konteks tematik embedding
    - title       : judul berita
    - tags        : topik/tag artikel
    - content     : isi artikel (dibatasi _EMBED_CONTENT_CHARS karakter pertama)
    """
    title       = (article.get("title",       "") or "").strip()
    tags        = (article.get("tags",        "") or "").strip()
    content     = (article.get("content",     "") or "").strip()
    kbli        = (article.get("kbli",        "") or "").strip()
    date_parsed = (article.get("date_parsed", "") or "").strip()
    date_raw    = (article.get("date",        "") or "").strip()

    # Pilih format tanggal: date_parsed (ISO YYYY-MM-DD) lebih bersih; fallback ke date raw
    tanggal = date_parsed or date_raw

    # Potong konten agar tidak melebihi batas token (bukan flat cut — ambil awal)
    if len(content) > _EMBED_CONTENT_CHARS:
        content = content[:_EMBED_CONTENT_CHARS]

    parts = []
    if tanggal:  parts.append(f"Tanggal: {tanggal}")
    if kbli:     parts.append(f"Kategori KBLI: {kbli}")
    if title:    parts.append(f"Judul: {title}")
    if tags:     parts.append(f"Topik: {tags}")
    if content:  parts.append(f"Konten: {content}")

    return "\n".join(parts)


# ── Embedding generation ───────────────────────────────────────────────────────

def generate_embedding(text: str, client: OpenAI | None = None) -> list[float] | None:
    """
    Generate embedding untuk satu teks.
    Return list[float] 1536 dimensi, atau None jika gagal.
    """
    if not text or not text.strip():
        return None

    try:
        _client = client or _build_embedding_client()
        response = _client.embeddings.create(
            model=_EMBEDDING_MODEL,
            input=text,
            dimensions=_EMBEDDING_DIMS,
            encoding_format="float",
        )
        data = getattr(response, "data", None)
        if not data or not isinstance(data, list):
            print("[Embedding] Respons embedding tidak valid: data kosong dari provider.")
            return None

        first = data[0] if data else None
        embedding = getattr(first, "embedding", None) if first is not None else None
        if not embedding:
            print("[Embedding] Respons embedding tidak valid: vektor kosong.")
            return None

        return embedding
    except Exception as exc:
        print(f"[Embedding] Gagal generate embedding: {exc}")
        return None


def embed_article(article: dict, client: OpenAI | None = None) -> list[float] | None:
    """
    Generate embedding untuk satu artikel (gabung title + tags + content).
    Return list[float] atau None jika gagal.
    """
    text = _prepare_text(article)
    if not text:
        return None
    return generate_embedding(text, client=client)


def batch_embed_texts(texts: list[str], client: OpenAI | None = None) -> list[list[float] | None]:
    """
    Generate embedding untuk banyak teks secara batch.
    Gemini mendukung multi-input dalam satu API call (lebih efisien).
    Return list dengan panjang sama dengan input — None untuk yang gagal.
    """
    if not texts:
        empty: list[list[float] | None] = []
        return empty

    _client    = client or _build_embedding_client()
    results: list[list[float] | None] = [None for _ in texts]
    total      = len(texts)

    for start in range(0, total, _BATCH_SIZE):
        batch      = texts[start : start + _BATCH_SIZE]
        batch_idxs = list(range(start, min(start + _BATCH_SIZE, total)))

        # Filter out empty texts agar tidak error di API
        non_empty   = [(i, t) for i, t in zip(batch_idxs, batch) if t and t.strip()]
        if not non_empty:
            continue

        try:
            idxs_valid, texts_valid = zip(*non_empty)
            response = _client.embeddings.create(
                model=_EMBEDDING_MODEL,
                input=list(texts_valid),
                dimensions=_EMBEDDING_DIMS,
                encoding_format="float",
            )
            data = getattr(response, "data", None)
            if not data or not isinstance(data, list):
                print(
                    f"[Embedding] Respons batch tidak valid untuk rentang {start + 1}-"
                    f"{start + len(batch)}: data kosong."
                )
            else:
                for emb_obj, original_idx in zip(data, idxs_valid):
                    emb = getattr(emb_obj, "embedding", None)
                    if emb:
                        results[original_idx] = emb

            end_idx = start + len(batch)
            print(f"[Embedding] Batch {start + 1}–{end_idx}/{total} selesai.")
        except Exception as exc:
            print(f"[Embedding] Gagal batch {start}–{start + len(batch)}: {exc}")

        if start + _BATCH_SIZE < total:
            time.sleep(_BATCH_SLEEP)

    return results


def batch_embed_articles(
    articles: list[dict], client: OpenAI | None = None
) -> list[list[float] | None]:
    """
    Generate embedding untuk banyak artikel sekaligus.
    Return list dengan panjang sama dengan input.
    """
    texts = [_prepare_text(a) for a in articles]
    return batch_embed_texts(texts, client=client)


# ── Semantic Search via Supabase RPC ──────────────────────────────────────────

def semantic_search(
    query:           str,
    supabase_client,                  # instance supabase-py client
    date_from:       str | None = None,
    date_to:         str | None = None,
    top_k:           int        = 30,
    min_similarity:  float      = 0.1,
    embed_client:    OpenAI | None = None,
) -> list[dict]:
    """
    Cari artikel paling relevan secara semantik menggunakan pgvector.

    Alur:
    1. Generate embedding untuk query text
    2. Panggil Supabase RPC `match_articles` dengan filter tanggal
    3. Return list artikel diurutkan by similarity (tertinggi lebih dulu)

    Return list[dict] dengan keys: id, title, date, url, content, tags, source, similarity
    Jika embedding gagal, return [] (caller harus handle fallback).
    """
    # Generate query embedding
    query_embedding = generate_embedding(query, client=embed_client)
    if query_embedding is None:
        print(f"[Embedding] Gagal generate query embedding untuk semantic search.")
        return []

    # Panggil Supabase RPC match_articles
    try:
        rpc_params: dict = {
            "query_embedding": query_embedding,
            "match_count":     top_k,
            "match_threshold": min_similarity,
        }
        if date_from:
            rpc_params["filter_date_from"] = date_from
        if date_to:
            rpc_params["filter_date_to"] = date_to

        result = supabase_client.rpc("match_articles", rpc_params).execute()
        return result.data or []

    except Exception as exc:
        print(f"[Embedding] Gagal semantic search via RPC: {exc}")
        return []


def semantic_search_multi(
    queries:         dict[str, str],   # {"pdrb": "...", "kemiskinan": "...", "pengangguran": "..."}
    supabase_client,
    date_from:       str | None = None,
    date_to:         str | None = None,
    top_k:           int        = 30,
    min_similarity:  float      = 0.1,
) -> dict[str, list[dict]]:
    """
    Jalankan semantic search untuk beberapa kategori secara PARALEL.
    Semua kategori embed + RPC call dijalankan bersamaan via ThreadPoolExecutor,
    memangkas waktu dari ~4.5 detik (sequential) menjadi ~1.5 detik (paralel).

    Gunakan satu embedding client yang di-share antar thread agar efisien.

    Return dict: {"pdrb": [...], "kemiskinan": [...], "pengangguran": [...]}
    """
    _client = _build_embedding_client()
    results: dict[str, list[dict]] = {}

    def _search_one(category: str, query: str) -> tuple[str, list[dict]]:
        """Jalankan satu kategori: embed query + RPC match_articles."""
        print(f"[Embedding] Semantic search: kategori={category}")
        hits = semantic_search(
            query           = query,
            supabase_client = supabase_client,
            date_from       = date_from,
            date_to         = date_to,
            top_k           = top_k,
            min_similarity  = min_similarity,
            embed_client    = _client,
        )
        print(f"[Embedding] -> {len(hits)} artikel relevan untuk '{category}'.")
        return category, hits

    # Jalankan semua kategori secara paralel
    with ThreadPoolExecutor(max_workers=len(queries)) as executor:
        futures = {
            executor.submit(_search_one, cat, q): cat
            for cat, q in queries.items()
        }
        for future in as_completed(futures):
            try:
                category, hits = future.result()
                results[category] = hits
            except Exception as exc:
                category = futures[future]
                print(f"[Embedding] Gagal semantic search untuk '{category}': {exc}")
                results[category] = []

    return results
