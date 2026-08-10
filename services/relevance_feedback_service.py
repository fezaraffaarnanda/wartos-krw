"""
Service layer untuk feedback loop classifier relevance (tahap-1).

Menyediakan:
  - override label manusia (ground truth)
  - antrian review (borderline / unlabeled / disagreement)
  - metrik precision/recall classifier vs label manusia
"""

from __future__ import annotations

from typing import Any

from repositories.berita import BeritaRepository
from repositories.relevance_prompt import RelevancePromptRepository

PROMPT_APPLY_CONFIRMATION = "yes, update system prompt"

_DRAFT_META_PROMPT = """Kamu adalah prompt engineer untuk classifier relevansi berita ekonomi.

Tugasmu: revisi SYSTEM_PROMPT classifier di bawah berdasarkan daftar kesalahan klasifikasi
(disagreement antara mesin dan label manusia).

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


class RelevanceFeedbackService:
    """Use-case audit & feedback classifier relevance, lepas dari Flask route."""

    def __init__(
        self,
        berita_repository: BeritaRepository | None = None,
        prompt_repository: RelevancePromptRepository | None = None,
    ):
        self._berita = berita_repository or BeritaRepository()
        self._prompts = prompt_repository or RelevancePromptRepository()

    def set_human_label(
        self,
        berita_id: int,
        *,
        is_relevant: bool,
        username: str,
    ) -> tuple[dict[str, Any], int]:
        if berita_id <= 0:
            return {"status": "error", "message": "ID tidak valid."}, 400

        row = self._berita.set_human_label(
            berita_id,
            is_relevant=is_relevant,
            username=username,
        )
        if not row:
            return {"status": "error", "message": "Berita tidak ditemukan / gagal disimpan."}, 404

        return {"status": "ok", "data": row}, 200

    def list_review_queue(
        self,
        *,
        mode: str = "borderline",
        page: int = 1,
        per_page: int = 25,
    ) -> tuple[dict[str, Any], int]:
        valid_modes = {"borderline", "unlabeled", "disagreement", "all"}
        if mode not in valid_modes:
            mode = "borderline"
        page = max(1, page)
        per_page = max(1, min(per_page, 100))

        result = self._berita.list_relevance_review_rows(
            mode=mode, page=page, per_page=per_page,
        )
        total_items = result["total_items"]
        return {
            "status": "ok",
            "mode": mode,
            "page": page,
            "per_page": per_page,
            "total_items": total_items,
            "total_pages": max(1, -(-total_items // per_page)),
            "data": result["data"],
        }, 200

    def export_few_shot(self, limit: int = 20) -> tuple[dict[str, Any], int]:
        """
        Ekspor kasus disagreement sebagai menu kurasi few-shot untuk prompt.

        Output berisi:
          - false_positives: mesin bilang relevan, manusia bilang tidak
          - false_negatives: mesin bilang tidak relevan, manusia bilang relevan
          - formatted_prompt: teks siap copy-paste ke SYSTEM_PROMPT (maks 6-8 contoh terbaik)

        Developer PILIH MANUAL mana contoh yang masuk prompt — jangan paste semua.
        Setelah paste, bump PROMPT_VERSION di ai/relevance.py.
        """
        rows = self._berita.list_disagreement_export_rows(limit)

        false_positives = [r for r in rows if bool(r.get("is_relevant")) and not bool(r.get("human_label"))]
        false_negatives = [r for r in rows if not bool(r.get("is_relevant")) and bool(r.get("human_label"))]

        def _format_entry(row: dict[str, Any], correction: str) -> str:
            title = (row.get("title") or "").strip()[:120]
            score = row.get("relevance_score", "?")
            reason = (row.get("relevance_reason") or "").strip()[:200]
            snippet = (row.get("content") or "").strip()[:120].replace("\n", " ")
            lines = [f'- "{title}"']
            lines.append(f'  Skor mesin: {score} → Koreksi: {correction}')
            if reason:
                lines.append(f'  Alasan mesin: "{reason}"')
            if snippet:
                lines.append(f'  Konteks: "{snippet}..."')
            return "\n".join(lines)

        fp_blocks = [_format_entry(r, "TIDAK RELEVAN") for r in false_positives]
        fn_blocks = [_format_entry(r, "RELEVAN") for r in false_negatives]

        sections: list[str] = [
            "=== MENU KURASI FEW-SHOT UNTUK SYSTEM_PROMPT ===",
            f"Total disagreement: {len(rows)} kasus "
            f"(FP={len(false_positives)}, FN={len(false_negatives)})",
            "",
            "PANDUAN: Pilih MAKS 6-8 contoh total (3-4 per tipe).",
            "Jangan paste semua — terlalu banyak contoh merusak performa LLM.",
            "Setelah paste ke SYSTEM_PROMPT, bump PROMPT_VERSION di ai/relevance.py.",
            "",
        ]

        if fp_blocks:
            sections.append("--- Contoh TIDAK RELEVAN (mesin salah: bilang relevan) ---")
            sections.extend(fp_blocks)
            sections.append("")

        if fn_blocks:
            sections.append("--- Contoh RELEVAN (mesin salah: bilang tidak relevan) ---")
            sections.extend(fn_blocks)
            sections.append("")

        if not fp_blocks and not fn_blocks:
            sections.append("Belum ada disagreement. Label lebih banyak berita dulu di halaman Audit Relevance.")

        formatted_prompt = "\n".join(sections)

        return {
            "status": "ok",
            "total_disagreements": len(rows),
            "false_positives": [
                {
                    "id": r.get("id"),
                    "title": r.get("title"),
                    "score": r.get("relevance_score"),
                    "reason": r.get("relevance_reason"),
                    "source": r.get("source"),
                }
                for r in false_positives
            ],
            "false_negatives": [
                {
                    "id": r.get("id"),
                    "title": r.get("title"),
                    "score": r.get("relevance_score"),
                    "reason": r.get("relevance_reason"),
                    "source": r.get("source"),
                }
                for r in false_negatives
            ],
            "formatted_prompt": formatted_prompt,
        }, 200

    # ── Prompt versioning (AI draft + typed confirmation) ────────────────────

    def get_prompt_info(self) -> tuple[dict[str, Any], int]:
        """Prompt aktif + riwayat versi."""
        from ai.relevance import get_active_prompt

        text, version = get_active_prompt()
        return {
            "status":   "ok",
            "version":  version,
            "prompt":   text,
            "versions": self._prompts.list_versions(),
        }, 200

    def generate_prompt_draft(self) -> tuple[dict[str, Any], int]:
        """
        Minta LLM menyusun draft SYSTEM_PROMPT baru berdasarkan disagreement.
        Tidak mengubah apa pun — hanya menghasilkan draft untuk direview admin.
        """
        import json as _json

        from ai.relevance import get_active_prompt
        from clients.llm import build_chat_client

        rows = self._berita.list_disagreement_export_rows(20)
        if not rows:
            return {
                "status": "error",
                "message": "Belum ada disagreement (label manusia vs mesin). "
                           "Label lebih banyak berita dulu di antrian review.",
            }, 400

        current_prompt, current_version = get_active_prompt()

        cases: list[str] = []
        for r in rows:
            machine = "RELEVAN" if r.get("is_relevant") else "TIDAK RELEVAN"
            human   = "RELEVAN" if r.get("human_label") else "TIDAK RELEVAN"
            title   = (r.get("title") or "").strip()[:120]
            reason  = (r.get("relevance_reason") or "").strip()[:200]
            snippet = (r.get("content") or "").strip()[:150].replace("\n", " ")
            cases.append(
                f'- "{title}"\n'
                f"  Mesin: {machine} (skor {r.get('relevance_score')}), Manusia: {human}\n"
                f'  Alasan mesin: "{reason}"\n'
                f'  Konteks: "{snippet}..."'
            )

        user_text = (
            f"SYSTEM_PROMPT SAAT INI (versi {current_version}):\n"
            f"-----\n{current_prompt}\n-----\n\n"
            f"DAFTAR KESALAHAN KLASIFIKASI ({len(rows)} kasus):\n" + "\n".join(cases)
        )

        try:
            client, model = build_chat_client()
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _DRAFT_META_PROMPT},
                    {"role": "user",   "content": user_text},
                ],
                temperature=0.3,
                max_tokens=4000,
                response_format={"type": "json_object"},
            )
            raw = (resp.choices[0].message.content or "").strip()
            data = _json.loads(raw)
        except Exception as exc:
            print(f"[PromptDraft] Gagal generate draft: {exc}")
            return {"status": "error", "message": f"Gagal generate draft: {exc}"}, 502

        draft = str(data.get("revised_prompt") or "").strip()
        notes = str(data.get("notes") or "").strip()
        if not draft or '"score"' not in draft:
            return {
                "status": "error",
                "message": "Draft dari LLM tidak valid (kosong / kehilangan format output JSON).",
            }, 502

        return {
            "status":              "ok",
            "current_version":     current_version,
            "current_prompt":      current_prompt,
            "next_version":        self._prompts.next_version(),
            "draft_prompt":        draft,
            "notes":               notes,
            "disagreement_count":  len(rows),
            "confirmation_phrase": PROMPT_APPLY_CONFIRMATION,
        }, 200

    def apply_prompt(
        self,
        *,
        draft_prompt: str,
        confirmation: str,
        username: str,
        notes: str = "",
    ) -> tuple[dict[str, Any], int]:
        """Aktifkan prompt baru. Wajib typed confirmation persis."""
        if (confirmation or "") != PROMPT_APPLY_CONFIRMATION:
            return {
                "status": "error",
                "message": f'Konfirmasi salah. Ketik persis: "{PROMPT_APPLY_CONFIRMATION}"',
            }, 400

        draft = (draft_prompt or "").strip()
        if len(draft) < 200 or '"score"' not in draft:
            return {
                "status": "error",
                "message": "Prompt tidak valid: terlalu pendek atau kehilangan format output JSON "
                           '(wajib mengandung "score").',
            }, 400

        version = self._prompts.next_version()
        row = self._prompts.insert_and_activate(
            version=version,
            prompt_text=draft,
            created_by=username,
            notes=notes,
        )
        if not row:
            return {"status": "error", "message": "Gagal menyimpan versi prompt baru."}, 500

        from ai.relevance import invalidate_prompt_cache
        invalidate_prompt_cache()

        return {
            "status":  "ok",
            "version": version,
            "message": f"Prompt {version} aktif. Klasifikasi berikutnya memakai prompt baru. "
                       "Row lama tetap bertag versi lama agar metrik antar versi bisa dibandingkan.",
        }, 200

    def metrics(self) -> tuple[dict[str, Any], int]:
        """Hitung confusion matrix + precision/recall (positive class = relevan)."""
        rows = self._berita.relevance_confusion_rows()

        tp = fp = tn = fn = 0
        for r in rows:
            machine = bool(r.get("is_relevant"))
            human   = bool(r.get("human_label"))
            if machine and human:
                tp += 1
            elif machine and not human:
                fp += 1
            elif not machine and not human:
                tn += 1
            else:  # not machine, human
                fn += 1

        labeled = tp + fp + tn + fn
        precision = tp / (tp + fp) if (tp + fp) else None
        recall    = tp / (tp + fn) if (tp + fn) else None
        accuracy  = (tp + tn) / labeled if labeled else None
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision and recall and (precision + recall)
            else None
        )

        return {
            "status": "ok",
            "labeled_count": labeled,
            "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
            "precision": precision,
            "recall": recall,
            "accuracy": accuracy,
            "f1": f1,
        }, 200
