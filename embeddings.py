"""
embeddings.py — Modul Vector Embedding untuk RAG

Mengelola pembuatan embedding artikel menggunakan OpenAI text-embedding-3-small
via OpenRouter API, dan semantic search via Supabase pgvector (RPC match_articles).
"""

import os
import time

from openai import OpenAI

# ── Konstanta ──────────────────────────────────────────────────────────────────

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_EMBEDDING_MODEL     = "openai/text-embedding-3-small"
_EMBEDDING_DIMS      = 1536

# Panjang konten artikel yang dipakai untuk embedding (lebih panjang = representasi lebih kaya)
_EMBED_CONTENT_CHARS = 2000

# Batch size untuk API call (OpenRouter support multi-input)
_BATCH_SIZE = 100

# Jeda antar batch (detik)
_BATCH_SLEEP = 0.3


# ── Client builder ─────────────────────────────────────────────────────────────

def _build_embedding_client() -> OpenAI:
    """Buat OpenAI client untuk embedding via OpenRouter menggunakan OPENROUTER_API_KEY."""
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY tidak ditemukan di environment variables.")
    return OpenAI(
        api_key  = api_key,
        base_url = _OPENROUTER_BASE_URL,
    )


# ── Teks preparation ───────────────────────────────────────────────────────────

def _prepare_text(article: dict) -> str:
    """
    Gabungkan judul, tags, dan konten artikel menjadi satu teks untuk di-embed.
    Format terstruktur membantu model memahami konteks setiap field.
    """
    title   = (article.get("title",   "") or "").strip()
    tags    = (article.get("tags",    "") or "").strip()
    content = (article.get("content", "") or "").strip()

    # Potong konten agar tidak melebihi batas token (bukan flat cut — ambil awal)
    if len(content) > _EMBED_CONTENT_CHARS:
        content = content[:_EMBED_CONTENT_CHARS]

    parts = []
    if title:
        parts.append(f"Judul: {title}")
    if tags:
        parts.append(f"Topik: {tags}")
    if content:
        parts.append(f"Konten: {content}")

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
            encoding_format="float",
        )
        return response.data[0].embedding
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
    OpenAI mendukung multi-input dalam satu API call (lebih efisien).
    Return list dengan panjang sama dengan input — None untuk yang gagal.
    """
    if not texts:
        return []

    _client    = client or _build_embedding_client()
    results    = [None] * len(texts)
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
                encoding_format="float",
            )
            for emb_obj, original_idx in zip(response.data, idxs_valid):
                results[original_idx] = emb_obj.embedding

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
    Jalankan semantic search untuk beberapa kategori sekaligus.
    Gunakan satu embedding client agar efisien (tidak re-init per kategori).

    Return dict: {"pdrb": [...], "kemiskinan": [...], "pengangguran": [...]}
    """
    _client = _build_embedding_client()
    results = {}

    for category, query in queries.items():
        print(f"[Embedding] Semantic search: kategori={category}")
        hits = semantic_search(
            query         = query,
            supabase_client = supabase_client,
            date_from     = date_from,
            date_to       = date_to,
            top_k         = top_k,
            min_similarity = min_similarity,
            embed_client  = _client,
        )
        results[category] = hits
        print(f"[Embedding] -> {len(hits)} artikel relevan untuk '{category}'.")

    return results
