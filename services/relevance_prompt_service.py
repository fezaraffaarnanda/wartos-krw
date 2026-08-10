"""
Service layer untuk siklus hidup prompt classifier relevance: draft, dry-run
eval, aktivasi, rollback. Dipisah dari relevance_feedback_service.py (yang
menangani labeling & metrik) karena keduanya punya kadar risiko berbeda --
apply_prompt mengubah perilaku klasifikasi produksi, set_human_label tidak.
"""

from __future__ import annotations

import json as _json
import time as _time
from typing import Any

from repositories.berita import BeritaRepository
from repositories.relevance_prompt import RelevancePromptRepository
from services.relevance_feedback_service import _f1_score

PROMPT_APPLY_CONFIRMATION = "yes, update system prompt"
MIN_LABELS_FOR_DRAFT = 12
MAX_EVAL_SAMPLE = 60

_DRAFT_META_PROMPT_CORRECTIVE = """Kamu adalah prompt engineer untuk classifier relevansi berita ekonomi.

Tugasmu: revisi SYSTEM_PROMPT classifier di bawah berdasarkan daftar kesalahan klasifikasi
(koreksi manusia terhadap keputusan mesin).

ATURAN KETAT:
1. PERTAHANKAN struktur rubrik 4 kriteria berbobot (total 100 poin) dan format output JSON
   {"score", "is_relevant", "reason"} persis seperti aslinya.
2. Perbaikan boleh berupa: penajaman deskripsi kriteria, penambahan/penggantian contoh few-shot.
3. Contoh few-shot MAKSIMAL 6-8 total. Jika prompt lama sudah punya contoh, GANTI yang lama
   dengan yang lebih representatif — jangan menumpuk.
4. Jangan menambah panjang prompt secara berlebihan (maksimal ~1.5x panjang asli).
5. Bahasa Indonesia, gaya konsisten dengan prompt asli.

Balas HANYA dalam format JSON valid:
{
  "revised_prompt": "<prompt lengkap hasil revisi>",
  "notes": "<2-3 kalimat ringkasan perubahan apa saja yang dilakukan dan kenapa>"
}"""

_DRAFT_META_PROMPT_REINFORCE = """Kamu adalah prompt engineer untuk classifier relevansi berita ekonomi.

Classifier saat ini SEPAKAT dengan seluruh label manusia yang tersedia -- tidak ada koreksi.
Tugasmu: mempertajam deskripsi kriteria dan mengganti contoh few-shot dengan kasus SULIT yang
sudah dikonfirmasi manusia (skor mendekati ambang 50 tapi keputusan mesin benar), agar rubrik
lebih tahan terhadap kasus serupa di masa depan.

ATURAN KETAT:
1. PERTAHANKAN struktur rubrik 4 kriteria berbobot (total 100 poin) dan format output JSON
   {"score", "is_relevant", "reason"} persis seperti aslinya.
2. JANGAN membalik keputusan mana pun -- classifier sudah benar pada semua kasus yang diberikan.
3. Contoh few-shot MAKSIMAL 6-8 total.
4. Jangan menambah panjang prompt secara berlebihan (maksimal ~1.5x panjang asli).
5. Bahasa Indonesia, gaya konsisten dengan prompt asli.

Balas HANYA dalam format JSON valid:
{
  "revised_prompt": "<prompt lengkap hasil revisi>",
  "notes": "<2-3 kalimat ringkasan perubahan apa saja yang dilakukan dan kenapa>"
}"""


def _validate_prompt_shape(text: str) -> bool:
    """Aturan validitas draft prompt -- satu implementasi dipakai draft, eval,
    dan apply, supaya ketiganya tidak diam-diam drift jadi tiga aturan berbeda."""
    return bool(text) and len(text) >= 200 and '"score"' in text


class RelevancePromptService:
    """Use-case siklus hidup prompt classifier relevance."""

    def __init__(
        self,
        berita_repository: BeritaRepository | None = None,
        prompt_repository: RelevancePromptRepository | None = None,
    ):
        self._berita = berita_repository or BeritaRepository()
        self._prompts = prompt_repository or RelevancePromptRepository()

    def get_prompt_info(self) -> tuple[dict[str, Any], int]:
        from ai.relevance import get_active_prompt

        text, version = get_active_prompt()
        active_row = self._prompts.get_active() or {}
        return {
            "status": "ok",
            "active": {
                "version": version,
                "prompt": text,
                "activated_at": active_row.get("activated_at"),
                "eval": active_row.get("eval_json") or {},
            },
            "versions": self._prompts.list_versions(),
        }, 200

    def generate_draft(self, *, limit: int = 20) -> tuple[dict[str, Any], int]:
        """Susun draft SYSTEM_PROMPT baru via LLM.

        400 HANYA bila total label < MIN_LABELS_FOR_DRAFT -- bukan bila
        koreksi == 0. Versi lama 400 setiap kali disagreement kosong, yang di
        data live SELALU terjadi (0 disagreement) sehingga tombol ini tidak
        pernah bisa dipakai. Mode 'reinforce' dipakai saat semua label
        konfirmasi (mesin sudah benar) untuk tetap menghasilkan draft yang
        berguna tanpa membalik keputusan yang sudah benar.
        """
        from ai.relevance import get_active_prompt
        from clients.llm import build_chat_client, log_usage, provider_from_model

        labeled = self._berita.list_labeled_rows(limit=1000, include_content=True)
        if len(labeled) < MIN_LABELS_FOR_DRAFT:
            return {
                "status": "error",
                "message": f"Baru {len(labeled)} label manusia. Butuh minimal {MIN_LABELS_FOR_DRAFT} "
                           "sebelum draft prompt bisa disusun. Label lebih banyak di antrian review.",
            }, 400

        corrections = [r for r in labeled if bool(r.get("human_label")) != bool(r.get("is_relevant"))]
        mode = "corrective" if corrections else "reinforce"
        meta_prompt = _DRAFT_META_PROMPT_CORRECTIVE if corrections else _DRAFT_META_PROMPT_REINFORCE
        source_rows = (corrections if corrections else labeled)[:limit]

        current_prompt, current_version = get_active_prompt()

        cases: list[str] = []
        for r in source_rows:
            machine = "RELEVAN" if r.get("is_relevant") else "TIDAK RELEVAN"
            human = "RELEVAN" if r.get("human_label") else "TIDAK RELEVAN"
            title = (r.get("title") or "").strip()[:120]
            reason = (r.get("relevance_reason") or "").strip()[:200]
            snippet = (r.get("content") or "").strip()[:150].replace("\n", " ")
            cases.append(
                f'- "{title}"\n'
                f"  Mesin: {machine} (skor {r.get('relevance_score')}), Manusia: {human}\n"
                f'  Alasan mesin: "{reason}"\n'
                f'  Konteks: "{snippet}..."'
            )

        case_label = "DAFTAR KESALAHAN KLASIFIKASI" if corrections else "DAFTAR KASUS SULIT YANG SUDAH BENAR"
        user_text = (
            f"SYSTEM_PROMPT SAAT INI (versi {current_version}):\n"
            f"-----\n{current_prompt}\n-----\n\n"
            f"{case_label} ({len(source_rows)} kasus):\n" + "\n".join(cases)
        )

        client, model = build_chat_client()
        provider = provider_from_model(model)
        t0 = _time.perf_counter()
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": meta_prompt},
                    {"role": "user", "content": user_text},
                ],
                temperature=0.3,
                # Besar (bukan sekadar cukup untuk output ~2-3k karakter): model
                # reasoning (mis. deepseek-v4-flash) menulis chain-of-thought ke
                # reasoning_content yang IKUT memotong budget max_tokens sebelum
                # sampai ke `content` -- dengan 4000 token habis semua terpakai
                # reasoning, `content` kosong dan JSON gagal parse (finish_reason
                # "length"). Longgar di sini, bukan di caller.
                max_tokens=16000,
                response_format={"type": "json_object"},
            )
            log_usage(
                feature="prompt_draft", provider=provider, model=model,
                usage=getattr(resp, "usage", None),
                latency_ms=(_time.perf_counter() - t0) * 1000,
            )
            raw = (resp.choices[0].message.content or "").strip()
            data = _json.loads(raw)
        except Exception as exc:
            log_usage(
                feature="prompt_draft", provider=provider, model=model,
                latency_ms=(_time.perf_counter() - t0) * 1000, success=False, error=str(exc),
            )
            print(f"[PromptDraft] Gagal generate draft: {exc}")
            return {"status": "error", "message": f"Gagal generate draft: {exc}"}, 502

        draft = str(data.get("revised_prompt") or "").strip()
        notes = str(data.get("notes") or "").strip()
        if not _validate_prompt_shape(draft):
            return {
                "status": "error",
                "message": "Draft dari LLM tidak valid (kosong / terlalu pendek / kehilangan format output JSON).",
            }, 502

        return {
            "status": "ok",
            "mode": mode,
            "current_version": current_version,
            "current_prompt": current_prompt,
            "next_version": self._prompts.next_version(),
            "draft_prompt": draft,
            "notes": notes,
            "evidence": {
                "corrections": len(corrections),
                "confirmations": len(labeled) - len(corrections),
                "total_labels": len(labeled),
            },
            "confirmation_phrase": PROMPT_APPLY_CONFIRMATION,
        }, 200

    def evaluate_draft(self, *, draft_prompt: str, sample_size: int = 40) -> tuple[dict[str, Any], int]:
        """Dry-run: jalankan draft DAN prompt aktif pada golden set yang sama
        (prioritas label_source='audit', diisi label_source lain bila
        kurang), tanpa mengubah apa pun. Membandingkan confusion matrix
        keduanya supaya aktivasi punya bukti, bukan tebakan."""
        from ai.relevance import classify_relevance, get_active_prompt
        from clients.llm import build_chat_client

        draft = (draft_prompt or "").strip()
        if not _validate_prompt_shape(draft):
            return {"status": "error", "message": "Draft tidak valid."}, 400

        sample_size = max(10, min(sample_size, MAX_EVAL_SAMPLE))
        audit_rows = self._berita.list_labeled_rows(limit=sample_size, include_content=True, label_source="audit")
        if len(audit_rows) < sample_size:
            seen_ids = {r["id"] for r in audit_rows}
            filler = self._berita.list_labeled_rows(limit=sample_size, include_content=True)
            audit_rows += [r for r in filler if r["id"] not in seen_ids][:sample_size - len(audit_rows)]
        rows = audit_rows[:sample_size]

        if not rows:
            return {"status": "error", "message": "Belum ada label manusia untuk uji kering."}, 400

        try:
            client, model = build_chat_client()
        except Exception as exc:
            return {"status": "error", "message": f"Gagal siapkan LLM client: {exc}"}, 502

        active_prompt, active_version = get_active_prompt()

        active_results: dict[int, dict[str, Any] | None] = {}
        draft_results: dict[int, dict[str, Any] | None] = {}
        for r in rows:
            active_results[r["id"]] = classify_relevance(
                r.get("content"), r.get("title"), client, model, prompt_override=active_prompt,
            )
            draft_results[r["id"]] = classify_relevance(
                r.get("content"), r.get("title"), client, model, prompt_override=draft,
            )

        def _confusion(results: dict[int, dict[str, Any] | None]) -> dict[str, Any]:
            tp = fp = tn = fn = 0
            for r in rows:
                res = results.get(r["id"])
                if res is None:
                    continue
                machine = bool(res["is_relevant"])
                human = bool(r.get("human_label"))
                if machine and human:
                    tp += 1
                elif machine and not human:
                    fp += 1
                elif not machine and not human:
                    tn += 1
                else:
                    fn += 1
            labeled = tp + fp + tn + fn
            precision = tp / (tp + fp) if (tp + fp) else None
            recall = tp / (tp + fn) if (tp + fn) else None
            accuracy = (tp + tn) / labeled if labeled else None
            return {"labeled_count": labeled, "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
                    "precision": precision, "recall": recall, "accuracy": accuracy,
                    "f1": _f1_score(precision, recall)}

        flips: list[dict[str, Any]] = []
        for r in rows:
            a = active_results.get(r["id"])
            d = draft_results.get(r["id"])
            if a is None or d is None:
                continue
            if bool(a["is_relevant"]) != bool(d["is_relevant"]):
                flips.append({
                    "id": r["id"],
                    "title": r.get("title"),
                    "active": a["is_relevant"],
                    "draft": d["is_relevant"],
                    "human": bool(r.get("human_label")),
                })

        return {
            "status": "ok",
            "sample_size": len(rows),
            "active": _confusion(active_results),
            "draft": _confusion(draft_results),
            "flips": flips,
            "cost_note": f"{len(rows)} baris x 2 panggilan LLM (aktif + draft).",
        }, 200

    def apply_prompt(
        self,
        *,
        draft_prompt: str,
        confirmation: str,
        username: str,
        notes: str = "",
        eval_result: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], int]:
        """Aktifkan prompt baru lewat RPC atomik. Wajib typed confirmation persis."""
        if (confirmation or "") != PROMPT_APPLY_CONFIRMATION:
            return {
                "status": "error",
                "message": f'Konfirmasi salah. Ketik persis: "{PROMPT_APPLY_CONFIRMATION}"',
            }, 400

        draft = (draft_prompt or "").strip()
        if not _validate_prompt_shape(draft):
            return {
                "status": "error",
                "message": "Prompt tidak valid: terlalu pendek atau kehilangan format output JSON "
                           '(wajib mengandung "score").',
            }, 400

        from ai.relevance import get_active_prompt
        _current_prompt, current_version = get_active_prompt()
        version = self._prompts.next_version()

        row = self._prompts.activate(
            version=version, prompt_text=draft, created_by=username, notes=notes,
            eval_result=eval_result, parent_version=current_version,
        )
        if not row:
            return {"status": "error", "message": "Gagal menyimpan versi prompt baru."}, 500

        from ai.relevance import invalidate_prompt_cache
        invalidate_prompt_cache()

        return {
            "status": "ok",
            "version": version,
            "eval_attached": bool(eval_result),
            "message": f"Prompt {version} aktif. Klasifikasi berikutnya memakai prompt baru. "
                       "Row lama tetap bertag versi lama agar metrik antar versi bisa dibandingkan.",
        }, 200

    def rollback_prompt(self, *, version: str, confirmation: str, username: str) -> tuple[dict[str, Any], int]:
        if (confirmation or "") != PROMPT_APPLY_CONFIRMATION:
            return {
                "status": "error",
                "message": f'Konfirmasi salah. Ketik persis: "{PROMPT_APPLY_CONFIRMATION}"',
            }, 400

        existing = self._prompts.get_by_version(version)
        if not existing:
            return {"status": "error", "message": f"Versi {version} tidak ditemukan."}, 404

        row = self._prompts.rollback_to(version)
        if not row:
            return {"status": "error", "message": f"Gagal rollback ke versi {version}."}, 500

        from ai.relevance import invalidate_prompt_cache
        invalidate_prompt_cache()

        return {
            "status": "ok",
            "version": version,
            "message": f"Rollback ke {version} berhasil (dipicu oleh {username}).",
        }, 200
