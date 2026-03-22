"""
Blueprint: AI Chat (RAG) — session, history, clear, non-stream, streaming.
"""

import json
from time import perf_counter

from flask import Blueprint, Response, jsonify, request, stream_with_context
from flask_login import current_user, login_required

from repositories.ai_chat import (
    AIChatRepository,
    _create_chat_session,
    _get_or_create_chat_session,
    _get_chat_session_owned,
    _load_chat_history,
    _save_chat_message,
)
from clients.supabase import supabase
from ai.chat import (
    extract_followup_questions,
    finalize_citations,
    generate_rag_answer,
    normalize_citation_markers,
    prepare_rag_chat_context,
    sanitize_answer_citation_tokens,
    stream_gemini_answer,
)
from config.extensions import limiter

ai_chat_bp = Blueprint("ai_chat", __name__)
_ai_chat_repo = AIChatRepository()


# ── Helper ───────────────────────────────────────────────────────────────────

def _current_user_id() -> int:
    return int(current_user.id)


def _serialize_cite_map(cite_map: dict[str, dict]) -> list[dict]:
    """Ubah map sitasi menjadi list agar mudah dikirim ke frontend."""
    items       = []
    ordered_keys = sorted(cite_map.keys())
    for idx, cid in enumerate(ordered_keys, 1):
        info = cite_map.get(cid) or {}
        items.append({"cite_id": cid, "num": idx, **info})
    return items


def _sse_payload(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ── Routes ───────────────────────────────────────────────────────────────────

@ai_chat_bp.route("/api/ai-chat/session", methods=["POST"])
@login_required
@limiter.limit("120 per hour")
def api_ai_chat_session():
    """Buat session baru atau ambil session terbaru milik user."""
    body      = request.get_json(silent=True) or {}
    force_new = bool(body.get("new", False))
    user_id   = _current_user_id()

    try:
        session = _create_chat_session(user_id) if force_new else _get_or_create_chat_session(user_id)
        return jsonify({"status": "ok", "session": session})
    except Exception as exc:
        return jsonify({"status": "error", "message": f"Gagal membuat session chat: {exc}"}), 500


@ai_chat_bp.route("/api/ai-chat/history", methods=["GET"])
@login_required
@limiter.limit("240 per hour")
def api_ai_chat_history():
    """Ambil riwayat chat untuk session milik user."""
    user_id        = _current_user_id()
    session_id_raw = request.args.get("session_id", "").strip()

    try:
        if session_id_raw:
            session_id = int(session_id_raw)
            session    = _get_chat_session_owned(user_id, session_id)
            if not session:
                return jsonify({"status": "error", "message": "Session chat tidak ditemukan."}), 404
        else:
            session    = _get_or_create_chat_session(user_id)
            session_id = int(session["id"])

        history = _load_chat_history(session_id, limit=60)
        return jsonify({"status": "ok", "session": session, "history": history})
    except Exception as exc:
        return jsonify({"status": "error", "message": f"Gagal mengambil riwayat chat: {exc}"}), 500


@ai_chat_bp.route("/api/ai-chat/clear", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def api_ai_chat_clear():
    """Hapus seluruh pesan dalam satu session chat milik user."""
    body           = request.get_json(silent=True) or {}
    user_id        = _current_user_id()
    session_id_raw = str(body.get("session_id", "")).strip()

    if not session_id_raw.isdigit():
        return jsonify({"status": "error", "message": "session_id tidak valid."}), 400

    session_id = int(session_id_raw)
    session    = _get_chat_session_owned(user_id, session_id)
    if not session:
        return jsonify({"status": "error", "message": "Session chat tidak ditemukan."}), 404

    try:
        _ai_chat_repo.clear_chat_messages(session_id)
        _ai_chat_repo.touch_chat_session(session_id)
        return jsonify({"status": "ok", "message": "Percakapan berhasil dibersihkan."})
    except Exception as exc:
        return jsonify({"status": "error", "message": f"Gagal membersihkan percakapan: {exc}"}), 500


@ai_chat_bp.route("/api/ai-chat", methods=["POST"])
@login_required
@limiter.limit("80 per hour")
def api_ai_chat():
    """Endpoint non-stream fallback untuk kompatibilitas."""
    body           = request.get_json(silent=True) or {}
    user_id        = _current_user_id()
    message        = str(body.get("message", "")).strip()
    session_id_raw = str(body.get("session_id", "")).strip()

    if not message:
        return jsonify({"status": "error", "message": "Pesan tidak boleh kosong."}), 400
    if len(message) > 1200:
        return jsonify({"status": "error", "message": "Pesan terlalu panjang. Maksimal 1200 karakter."}), 400

    try:
        if session_id_raw and session_id_raw.isdigit():
            session_id = int(session_id_raw)
            session    = _get_chat_session_owned(user_id, session_id)
            if not session:
                return jsonify({"status": "error", "message": "Session chat tidak ditemukan."}), 404
        else:
            session    = _get_or_create_chat_session(user_id)
            session_id = int(session["id"])

        history = _load_chat_history(session_id, limit=20)
        _save_chat_message(session_id, "user", message, citations=[])

        t0     = perf_counter()
        result = generate_rag_answer(
            query           = message,
            supabase_client = supabase,
            history         = history,
        )
        total_ms = result.get("total_ms", (perf_counter() - t0) * 1000)
        print(
            "[AI Chat] non-stream "
            f"retrieve={result.get('retrieve_ms', 0.0):.1f}ms "
            f"llm={result.get('llm_ms', 0.0):.1f}ms "
            f"total={total_ms:.1f}ms"
        )

        answer       = result.get("answer", "")
        citations_raw = result.get("citations", [])
        citation_nums = {
            c.get("cite_id"): idx + 1
            for idx, c in enumerate(citations_raw)
            if c.get("cite_id")
        }
        citations = [
            {**c, "num": citation_nums.get(c.get("cite_id"), idx + 1)}
            for idx, c in enumerate(citations_raw)
        ]
        _save_chat_message(session_id, "assistant", answer, citations=citations)

        return jsonify({
            "status":     "ok",
            "session_id": session_id,
            "answer":     answer,
            "citations":  citations,
            "used_docs":  result.get("used_docs", 0),
            "latency_ms": total_ms,
        })
    except Exception as exc:
        return jsonify({"status": "error", "message": f"Gagal memproses chat AI: {exc}"}), 500


@ai_chat_bp.route("/api/ai-chat/stream", methods=["POST"])
@login_required
@limiter.limit("80 per hour")
def api_ai_chat_stream():
    """Endpoint streaming token (SSE) untuk UX chat auto-typing."""
    body           = request.get_json(silent=True) or {}
    user_id        = _current_user_id()
    message        = str(body.get("message", "")).strip()
    session_id_raw = str(body.get("session_id", "")).strip()

    if not message:
        return jsonify({"status": "error", "message": "Pesan tidak boleh kosong."}), 400
    if len(message) > 1200:
        return jsonify({"status": "error", "message": "Pesan terlalu panjang. Maksimal 1200 karakter."}), 400

    try:
        if session_id_raw and session_id_raw.isdigit():
            session_id = int(session_id_raw)
            session    = _get_chat_session_owned(user_id, session_id)
            if not session:
                return jsonify({"status": "error", "message": "Session chat tidak ditemukan."}), 404
        else:
            session    = _get_or_create_chat_session(user_id)
            session_id = int(session["id"])
    except Exception as exc:
        return jsonify({"status": "error", "message": f"Gagal menyiapkan session chat: {exc}"}), 500

    history = _load_chat_history(session_id, limit=20)
    _save_chat_message(session_id, "user", message, citations=[])

    @stream_with_context
    def generate_events():
        total_start = perf_counter()
        try:
            prepared = prepare_rag_chat_context(
                query           = message,
                supabase_client = supabase,
                history         = history,
            )

            retrieve_ms = float(prepared.get("retrieve_ms", 0.0))
            used_docs   = int(prepared.get("used_docs", 0))

            if prepared["status"] != "ok":
                answer = prepared.get("answer", "Data tidak cukup.")
                _save_chat_message(session_id, "assistant", answer, citations=[])
                yield _sse_payload({"type": "start", "session_id": session_id, "sources": []})
                yield _sse_payload({"type": "delta", "text": answer})
                yield _sse_payload({
                    "type":       "done",
                    "session_id": session_id,
                    "citations":  [],
                    "used_docs":  used_docs,
                    "latency": {
                        "retrieve_ms": retrieve_ms,
                        "llm_ms":      0.0,
                        "total_ms":    retrieve_ms,
                    },
                })
                return

            cite_map = prepared["cite_map"]
            yield _sse_payload({
                "type":       "start",
                "session_id": session_id,
                "sources":    _serialize_cite_map(cite_map),
                "used_docs":  used_docs,
            })

            llm_start   = perf_counter()
            chunks: list[str] = []
            for delta in stream_gemini_answer(
                prepared["user_prompt"],
                history=prepared.get("history", []),
            ):
                chunks.append(delta)
                yield _sse_payload({"type": "delta", "text": delta})

            llm_ms      = (perf_counter() - llm_start) * 1000
            answer_raw  = "".join(chunks).strip()
            answer_norm = normalize_citation_markers(answer_raw)
            answer_full = sanitize_answer_citation_tokens(answer_norm, cite_map)
            if not answer_full:
                answer_full = "Terjadi kendala saat memproses chat AI. Silakan coba beberapa saat lagi."

            answer, follow_ups = extract_followup_questions(answer_full)
            if not answer:
                answer = answer_full

            citations_raw = finalize_citations(answer, cite_map)
            source_items  = _serialize_cite_map(cite_map)
            source_num_map = {s.get("cite_id"): s.get("num") for s in source_items}
            citations = [
                {**c, "num": source_num_map.get(c.get("cite_id"), idx + 1)}
                for idx, c in enumerate(citations_raw)
            ]
            _save_chat_message(session_id, "assistant", answer, citations=citations)

            total_ms = (perf_counter() - total_start) * 1000
            print(
                "[AI Chat] stream "
                f"retrieve={retrieve_ms:.1f}ms llm={llm_ms:.1f}ms total={total_ms:.1f}ms"
            )

            yield _sse_payload({
                "type":       "done",
                "session_id": session_id,
                "citations":  citations,
                "follow_ups": follow_ups,
                "used_docs":  used_docs,
                "latency": {
                    "retrieve_ms": round(retrieve_ms, 1),
                    "llm_ms":      round(llm_ms, 1),
                    "total_ms":    round(total_ms, 1),
                },
            })

        except Exception as exc:
            print(f"[AI Chat] stream error: {exc}")
            err_msg = "Gagal memproses chat AI. Silakan coba beberapa saat lagi."
            try:
                _save_chat_message(session_id, "assistant", err_msg, citations=[])
            except Exception:
                pass
            yield _sse_payload({"type": "error", "message": err_msg})

    return Response(
        generate_events(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":       "keep-alive",
        },
    )
