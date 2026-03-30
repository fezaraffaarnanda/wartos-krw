"""
Blueprint: AI Insights — polling endpoint dan SSE streaming.
"""

import json
import threading
from datetime import datetime, timedelta, timezone
from time import perf_counter

from flask import Blueprint, Response, jsonify, request, stream_with_context
from flask_login import login_required

from ai.insights import (
    build_stream_category_context,
    extract_sources_from_markers,
    generate_insights,
    normalize_inline_markers,
    prepare_insight_articles,
    stream_category_tokens,
    _ACTOR_PROMPTS,
    _SYSTEM_PROMPT_BPS,
)
from repositories.ai_insights import (
    _fetch_period_articles,
    _load_insight_from_db,
    _save_insight_to_db,
)
from clients.llm import build_chat_client
from state.insights import _INSIGHTS_CACHE, _INSIGHTS_GENERATING
from config.extensions import limiter
from utils.date import WIB

ai_insights_bp = Blueprint("ai_insights", __name__)


# ── Helper: period range ─────────────────────────────────────────────────────

def _get_period_range(period: str, year: int | None = None) -> tuple[str, str, str, str]:
    """
    Kembalikan (period_key, period_label, date_from, date_to).
    Opsi period: q1/q2/q3/q4, s1/s2, yearly.
    """
    now          = datetime.now(WIB)
    current_year = now.year
    y            = year if year else current_year
    month        = now.month

    _PERIODS = {
        "q1":     (f"q1_{y}",     f"Triwulan I {y} (Jan–Mar)",      f"{y}-01-01", f"{y}-03-31"),
        "q2":     (f"q2_{y}",     f"Triwulan II {y} (Apr–Jun)",      f"{y}-04-01", f"{y}-06-30"),
        "q3":     (f"q3_{y}",     f"Triwulan III {y} (Jul–Sep)",     f"{y}-07-01", f"{y}-09-30"),
        "q4":     (f"q4_{y}",     f"Triwulan IV {y} (Okt–Des)",      f"{y}-10-01", f"{y}-12-31"),
        "s1":     (f"s1_{y}",     f"Semester I {y} (Jan–Jun)",       f"{y}-01-01", f"{y}-06-30"),
        "s2":     (f"s2_{y}",     f"Semester II {y} (Jul–Des)",      f"{y}-07-01", f"{y}-12-31"),
        "yearly": (f"yearly_{y}", f"Tahunan {y} (Jan–Des)",          f"{y}-01-01", f"{y}-12-31"),
    }

    if period in _PERIODS:
        return _PERIODS[period]

    if y == current_year:
        if month <= 3:    return _PERIODS["q1"]
        elif month <= 6:  return _PERIODS["q2"]
        elif month <= 9:  return _PERIODS["q3"]
        else:             return _PERIODS["q4"]

    return _PERIODS["yearly"]


# ── Helper: SSE payload ──────────────────────────────────────────────────────

def _sse_payload(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ── Background worker untuk polling endpoint ─────────────────────────────────

def _generate_insights_worker(
    period_key:   str,
    period_label: str,
    date_from:    str,
    date_to:      str,
    articles:     list,
) -> None:
    """
    Worker thread: generate_insights() di background lalu simpan ke cache & DB.
    """
    import time as _time
    print(f"[AI Insights] Worker thread dimulai untuk {period_key} ({len(articles)} artikel).")
    try:
        from clients.supabase import supabase as _supabase
        insights = generate_insights(
            period_label    = period_label,
            date_from       = date_from,
            date_to         = date_to,
            supabase_client = _supabase,
            articles        = articles,
        )

        _save_insight_to_db(period_key, period_label, insights, len(articles))

        payload = {
            "status":        "ok",
            "cached":        False,
            "quarter":       period_label,
            "article_count": len(articles),
            "data": {
                "pdrb":         insights["pdrb"],
                "kemiskinan":   insights["kemiskinan"],
                "pengangguran": insights["pengangguran"],
            },
            "sources": insights.get("sources", {}),
        }
        _INSIGHTS_CACHE[period_key] = {"ts": _time.time(), "data": payload}
        _INSIGHTS_GENERATING[period_key] = False
        print(f"[AI Insights] Worker selesai untuk {period_key}.")

    except Exception as exc:
        _INSIGHTS_GENERATING[period_key] = f"error: {exc}"
        print(f"[AI Insights] Worker error untuk {period_key}: {exc}")


# ── Routes ───────────────────────────────────────────────────────────────────

@ai_insights_bp.route("/api/ai-insights", methods=["GET"])
@login_required
@limiter.limit("30 per hour")
def get_ai_insights():
    """
    Hasilkan insight AI untuk PDRB, Kemiskinan, Pengangguran.

    Query params:
      period  — q1/q2/q3/q4/s1/s2/yearly (default: triwulan berjalan)
      year    — tahun (default: tahun berjalan)
      refresh — 1 untuk paksa regenerasi
      poll    — 1 untuk cek status background thread
      actor   — bps/pemerintah/akademisi (default: bps)
    """
    period        = request.args.get("period", "").strip().lower()
    force_refresh = request.args.get("refresh", "") == "1"
    poll_request  = request.args.get("poll", "") == "1"
    year_str      = request.args.get("year", "").strip()
    year          = int(year_str) if year_str.isdigit() else None
    actor         = request.args.get("actor", "bps").strip().lower()
    if actor not in _ACTOR_PROMPTS:
        actor = "bps"

    period_key, period_label, date_from, date_to = _get_period_range(period, year)
    actor_period_key = period_key if actor == "bps" else f"{actor}_{period_key}"

    gen_state = _INSIGHTS_GENERATING.get(actor_period_key)
    db_row    = _load_insight_from_db(actor_period_key)

    if isinstance(gen_state, str) and gen_state.startswith("error"):
        error_msg = gen_state[len("error: "):]
        print(f"[AI Insights] Thread sebelumnya gagal untuk {actor_period_key}: {error_msg}")
        return jsonify({
            "status":  "error",
            "message": f"Gagal menghasilkan insight: {error_msg}",
        }), 500

    if poll_request:
        if gen_state is True:
            print(f"[AI Insights] Poll: thread masih berjalan untuk {actor_period_key}.")
            return jsonify({"status": "generating"})

        if db_row:
            print(f"[AI Insights] Poll: hasil DB siap untuk {actor_period_key}.")
            return jsonify({
                "status":        "ok",
                "cached":        True,
                "quarter":       db_row["period_label"],
                "article_count": db_row["article_count"],
                "data": {
                    "pdrb":         db_row["pdrb"],
                    "kemiskinan":   db_row["kemiskinan"],
                    "pengangguran": db_row["pengangguran"],
                },
                "sources":      db_row["sources"],
                "generated_at": db_row["created_at"],
            })

        ready = _INSIGHTS_CACHE.get(actor_period_key)
        if ready:
            print(f"[AI Insights] Poll: hasil siap untuk {actor_period_key}.")
            return jsonify(ready["data"])

        print(f"[AI Insights] Poll: belum ada hasil untuk {actor_period_key}.")
        return jsonify({"status": "generating"})

    if db_row:
        if force_refresh:
            print(f"[AI Insights] Refresh diabaikan karena data DB sudah ada untuk {actor_period_key}.")
        else:
            print(f"[AI Insights] Ambil hasil dari DB untuk {actor_period_key}.")
        return jsonify({
            "status":        "ok",
            "cached":        True,
            "quarter":       db_row["period_label"],
            "article_count": db_row["article_count"],
            "data": {
                "pdrb":         db_row["pdrb"],
                "kemiskinan":   db_row["kemiskinan"],
                "pengangguran": db_row["pengangguran"],
            },
            "sources":      db_row["sources"],
            "generated_at": db_row["created_at"],
        })

    if gen_state is True:
        print(f"[AI Insights] Thread masih berjalan untuk {actor_period_key} — return generating.")
        return jsonify({"status": "generating"})

    articles = _fetch_period_articles(date_from, date_to)

    _INSIGHTS_GENERATING[actor_period_key] = True
    threading.Thread(
        target  = _generate_insights_worker,
        args    = (actor_period_key, period_label, date_from, date_to, articles),
        daemon  = True,
        name    = f"ai-insights-{actor_period_key}",
    ).start()
    print(f"[AI Insights] Thread spawned untuk {actor_period_key} ({len(articles)} artikel) — return generating.")
    return jsonify({"status": "generating"})


@ai_insights_bp.route("/api/ai-insights/stream", methods=["GET"])
@login_required
@limiter.limit("20 per hour")
def stream_ai_insights():
    """Streaming insight AI via SSE (token-by-token) untuk UX realtime."""
    period        = request.args.get("period", "").strip().lower()
    force_refresh = request.args.get("refresh", "") == "1"
    year_str      = request.args.get("year", "").strip()
    year          = int(year_str) if year_str.isdigit() else None
    actor         = request.args.get("actor", "bps").strip().lower()
    if actor not in _ACTOR_PROMPTS:
        actor = "bps"

    period_key, period_label, date_from, date_to = _get_period_range(period, year)
    actor_period_key = period_key if actor == "bps" else f"{actor}_{period_key}"

    db_row = _load_insight_from_db(actor_period_key)
    if db_row and not force_refresh:
        payload = {
            "status":        "ok",
            "cached":        True,
            "quarter":       db_row["period_label"],
            "article_count": db_row["article_count"],
            "data": {
                "pdrb":         db_row["pdrb"],
                "kemiskinan":   db_row["kemiskinan"],
                "pengangguran": db_row["pengangguran"],
            },
            "sources":      db_row["sources"],
            "generated_at": db_row["created_at"],
        }

        def _cached_stream():
            yield _sse_payload({"type": "start", "quarter": db_row["period_label"], "article_count": db_row["article_count"], "cached": True})
            yield _sse_payload({"type": "done", **payload})

        return Response(
            stream_with_context(_cached_stream()),
            mimetype="text/event-stream",
            headers={
                "Cache-Control":    "no-cache",
                "X-Accel-Buffering": "no",
                "Connection":       "keep-alive",
            },
        )

    articles = _fetch_period_articles(date_from, date_to)

    @stream_with_context
    def _generate_stream():
        total_start = perf_counter()
        try:
            from clients.supabase import supabase as _supabase
            prepared = prepare_insight_articles(
                period_label    = period_label,
                date_from       = date_from,
                date_to         = date_to,
                supabase_client = _supabase,
                articles        = articles or [],
            )

            article_count = int(prepared.get("article_count", 0))
            yield _sse_payload({
                "type":          "start",
                "quarter":       period_label,
                "article_count": article_count,
                "cached":        False,
            })

            client, _chat_model = build_chat_client()
            actor_system_prompt = _ACTOR_PROMPTS.get(actor, _SYSTEM_PROMPT_BPS)
            categories          = ("pdrb", "kemiskinan", "pengangguran")
            final_data:    dict[str, str]        = {}
            final_sources: dict[str, list[dict]] = {}

            for cat in categories:
                cat_articles = prepared.get(cat, []) or []
                if not cat_articles:
                    official_text = str(
                        ((prepared.get("official_statistics") or {}).get("topics") or {}).get(cat) or ""
                    ).strip()
                    text = "Data berita periode ini belum cukup untuk analisis mendalam pada kategori ini."
                    if official_text:
                        text = f"{text}\n\n{official_text}"
                    final_data[cat]    = text
                    final_sources[cat] = []
                    yield _sse_payload({"type": "category_start", "category": cat, "source_map": []})
                    yield _sse_payload({"type": "category_done", "category": cat, "text": text, "sources": []})
                    continue

                ctx        = build_stream_category_context(
                    cat,
                    period_label,
                    cat_articles,
                    actor=actor,
                    official_statistics=prepared.get("official_statistics"),
                )
                source_map = ctx["source_map"]
                yield _sse_payload({"type": "category_start", "category": cat, "source_map": source_map})

                chunks: list[str] = []
                for delta in stream_category_tokens(
                    client        = client,
                    model         = _chat_model,
                    user_prompt   = ctx["prompt"],
                    system_prompt = actor_system_prompt,
                ):
                    chunks.append(delta)
                    yield _sse_payload({"type": "delta", "category": cat, "text": delta})

                raw_text   = "".join(chunks).strip()
                cat_prefix = {"pdrb": "P", "kemiskinan": "K", "pengangguran": "T"}.get(cat, "P")
                normalized = normalize_inline_markers(raw_text, prefixes="PKT", single_prefix=cat_prefix)
                if not normalized:
                    normalized = "Data berita periode ini belum cukup untuk analisis mendalam pada kategori ini."

                used_sources = extract_sources_from_markers(normalized, source_map)
                if not used_sources:
                    used_sources = source_map[:2]

                final_data[cat]    = normalized
                final_sources[cat] = used_sources

                yield _sse_payload({
                    "type":     "category_done",
                    "category": cat,
                    "text":     normalized,
                    "sources":  used_sources,
                })

            insights_payload = {
                "pdrb":         final_data.get("pdrb", ""),
                "kemiskinan":   final_data.get("kemiskinan", ""),
                "pengangguran": final_data.get("pengangguran", ""),
                "sources":      final_sources,
            }
            _save_insight_to_db(actor_period_key, period_label, insights_payload, article_count)

            total_ms     = (perf_counter() - total_start) * 1000
            done_payload = {
                "status":        "ok",
                "cached":        False,
                "quarter":       period_label,
                "article_count": article_count,
                "data": {
                    "pdrb":         insights_payload["pdrb"],
                    "kemiskinan":   insights_payload["kemiskinan"],
                    "pengangguran": insights_payload["pengangguran"],
                },
                "sources":    final_sources,
                "latency_ms": {"total": round(total_ms, 1)},
            }
            _INSIGHTS_CACHE[actor_period_key] = {"ts": 0.0, "data": done_payload}
            yield _sse_payload({"type": "done", **done_payload})

        except Exception as exc:
            print(f"[AI Insights] Stream error {actor_period_key}: {exc}")
            yield _sse_payload({
                "type":    "error",
                "message": f"Gagal menghasilkan insight AI: {exc}",
            })

    return Response(
        _generate_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":       "keep-alive",
        },
    )
