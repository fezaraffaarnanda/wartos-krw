"""
Service layer untuk labeling & metrik classifier relevance (tahap-1).

Siklus hidup prompt (draft/eval/apply/rollback) ada di
services/relevance_prompt_service.py -- file ini murni antrian review,
label manusia, undo, re-classify, dan metrik.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from repositories.berita import BeritaRepository
from repositories.relevance_audit import RelevanceAuditRepository
from repositories.relevance_label_event import RelevanceLabelEventRepository

_QUEUE_MODES = {"uncertainty", "audit", "failed", "labeled", "disagreement", "all"}
_SCORE_BANDS = ("b00_19", "b20_39", "b40_59", "b60_79", "b80_100")
MAX_BULK_LABEL = 50
MIN_AUDIT_LABELS_FOR_METRICS = 30


def _band_for_score(score: int | None) -> str | None:
    if score is None:
        return None
    if score <= 19:
        return "b00_19"
    if score <= 39:
        return "b20_39"
    if score <= 59:
        return "b40_59"
    if score <= 79:
        return "b60_79"
    return "b80_100"


def _confusion_counts(rows: list[dict[str, Any]]) -> tuple[int, int, int, int]:
    tp = fp = tn = fn = 0
    for r in rows:
        machine = bool(r.get("is_relevant"))
        human = bool(r.get("human_label"))
        if machine and human:
            tp += 1
        elif machine and not human:
            fp += 1
        elif not machine and not human:
            tn += 1
        else:
            fn += 1
    return tp, fp, tn, fn


def _f1_score(precision: float | None, recall: float | None) -> float | None:
    """F1 dari precision/recall, mengikuti konvensi standar (mis. scikit-learn):
    precision=recall=0.0 (classifier terburuk, tp=0) -> F1=0.0, BUKAN None.

    Defect lama: `if precision and recall` menganggap 0.0 sebagai falsy,
    sehingga classifier terburuk (precision=recall=0.0) balas F1=None ("—" di
    UI) alih-alih 0.0. Percobaan perbaikan pertama di sini (`(p+r) > 0`) masih
    salah dengan cara sama: precision=0 SELALU membuat recall=0 juga (tp
    dibagi di kedua rumus), jadi (p+r)>0 gagal persis di kasus yang justru mau
    diperbaiki. F1 hanya None kalau precision ATAU recall memang tak
    terdefinisi (denominator asli nol -- belum ada label sama sekali)."""
    if precision is None or recall is None:
        return None
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _confusion_block(rows: list[dict[str, Any]]) -> dict[str, Any]:
    tp, fp, tn, fn = _confusion_counts(rows)
    labeled = tp + fp + tn + fn
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    accuracy = (tp + tn) / labeled if labeled else None
    f1 = _f1_score(precision, recall)

    return {
        "labeled_count": labeled,
        "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "precision": precision,
        "recall": recall,
        "accuracy": accuracy,
        "f1": f1,
    }


def _weighted_confusion_block(rows: list[dict[str, Any]], band_population: dict[str, int]) -> dict[str, Any]:
    """Confusion matrix berbobot strata -- w_band = populasi_band / label_di_band.
    Ini yang membuat sampel audit (bukan antrian terarah) memberi estimasi
    performa korpus, bukan performa band yang paling meragukan saja."""
    labeled_in_band: dict[str, int] = defaultdict(int)
    for r in rows:
        band = _band_for_score(r.get("relevance_score"))
        if band:
            labeled_in_band[band] += 1

    wtp = wfp = wtn = wfn = 0.0
    for r in rows:
        band = _band_for_score(r.get("relevance_score"))
        pop = band_population.get(band, 0) if band else 0
        lab = labeled_in_band.get(band, 0) if band else 0
        weight = (pop / lab) if lab else 0.0

        machine = bool(r.get("is_relevant"))
        human = bool(r.get("human_label"))
        if machine and human:
            wtp += weight
        elif machine and not human:
            wfp += weight
        elif not machine and not human:
            wtn += weight
        else:
            wfn += weight

    precision = wtp / (wtp + wfp) if (wtp + wfp) else None
    recall = wtp / (wtp + wfn) if (wtp + wfn) else None
    total_w = wtp + wfp + wtn + wfn
    accuracy = (wtp + wtn) / total_w if total_w else None
    f1 = _f1_score(precision, recall)

    return {
        "labeled_count": len(rows),
        "confusion_weighted": {
            "tp": round(wtp, 2), "fp": round(wfp, 2), "tn": round(wtn, 2), "fn": round(wfn, 2),
        },
        "precision": precision,
        "recall": recall,
        "accuracy": accuracy,
        "f1": f1,
    }


def _metrics_by_version(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_version: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_version[r.get("relevance_prompt_version") or "unknown"].append(r)
    out = [{"version": v, **_confusion_block(vrows)} for v, vrows in by_version.items()]
    out.sort(key=lambda x: x["version"], reverse=True)
    return out


def _export_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "title": row.get("title"),
        "score": row.get("relevance_score"),
        "reason": row.get("relevance_reason"),
        "source": row.get("source"),
    }


class RelevanceFeedbackService:
    """Use-case audit & feedback classifier relevance, lepas dari Flask route."""

    def __init__(
        self,
        berita_repository: BeritaRepository | None = None,
        label_event_repository: RelevanceLabelEventRepository | None = None,
        audit_repository: RelevanceAuditRepository | None = None,
    ):
        self._berita = berita_repository or BeritaRepository()
        self._events = label_event_repository or RelevanceLabelEventRepository()
        self._audit = audit_repository or RelevanceAuditRepository()

    # ── Antrian review ────────────────────────────────────────────────────────

    def list_review_queue(
        self,
        *,
        mode: str = "uncertainty",
        page: int = 1,
        per_page: int = 25,
        search: str = "",
        source: str = "",
        score_min: int | None = None,
        score_max: int | None = None,
    ) -> tuple[dict[str, Any], int]:
        if mode not in _QUEUE_MODES:
            mode = "uncertainty"
        page = max(1, page)
        per_page = max(1, min(per_page, 100))

        audit_ids = None
        if mode == "audit":
            batch = self._audit.get_open_batch()
            audit_ids = self._audit.list_batch_item_ids(batch["id"], unlabeled_only=True) if batch else []

        result = self._berita.list_relevance_review_rows(
            mode=mode, page=page, per_page=per_page,
            search=search, source=source, score_min=score_min, score_max=score_max,
            audit_berita_ids=audit_ids,
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

    def get_review_item(self, berita_id: int) -> tuple[dict[str, Any], int]:
        if berita_id <= 0:
            return {"status": "error", "message": "ID tidak valid."}, 400
        row = self._berita.get_relevance_item(berita_id)
        if not row:
            return {"status": "error", "message": "Berita tidak ditemukan."}, 404
        history = self._events.list_for_berita(berita_id, limit=10)
        return {"status": "ok", "data": row, "label_history": history}, 200

    # ── Label manusia ─────────────────────────────────────────────────────────

    def set_human_label(
        self,
        berita_id: int,
        *,
        is_relevant: bool,
        username: str,
        label_source: str = "targeted",
        note: str = "",
    ) -> tuple[dict[str, Any], int]:
        if berita_id <= 0:
            return {"status": "error", "message": "ID tidak valid."}, 400

        current = self._berita.get_relevance_item(berita_id)
        if not current:
            return {"status": "error", "message": "Berita tidak ditemukan."}, 404

        row = self._berita.set_human_label(
            berita_id, is_relevant=is_relevant, username=username,
            label_source=label_source, note=note,
        )
        if not row:
            return {"status": "error", "message": "Gagal menyimpan label."}, 500

        self._events.record(
            berita_id=berita_id,
            previous_label=current.get("human_label"),
            new_label=is_relevant,
            label_source=label_source,
            note=note,
            machine_label=current.get("is_relevant"),
            machine_score=current.get("relevance_score"),
            prompt_version=current.get("relevance_prompt_version"),
            actor_username=username,
        )

        if label_source == "audit":
            batch = self._audit.get_open_batch()
            if batch:
                self._audit.mark_item_labeled(batch_id=batch["id"], berita_id=berita_id)

        return {"status": "ok", "data": row}, 200

    def clear_human_label(self, berita_id: int, *, username: str) -> tuple[dict[str, Any], int]:
        """Hapus label (undo eksplisit dari tombol, bukan lewat riwayat event)."""
        if berita_id <= 0:
            return {"status": "error", "message": "ID tidak valid."}, 400

        current = self._berita.get_relevance_item(berita_id)
        if not current:
            return {"status": "error", "message": "Berita tidak ditemukan."}, 404
        if current.get("human_label") is None:
            return {"status": "ok", "data": {"id": berita_id, "human_label": None}}, 200

        row = self._berita.set_human_label(berita_id, is_relevant=None, username=username)
        if row is None:
            return {"status": "error", "message": "Gagal menghapus label."}, 500

        self._events.record(
            berita_id=berita_id,
            previous_label=current.get("human_label"),
            new_label=None,
            label_source=current.get("label_source") or "targeted",
            note="clear",
            machine_label=current.get("is_relevant"),
            machine_score=current.get("relevance_score"),
            prompt_version=current.get("relevance_prompt_version"),
            actor_username=username,
        )
        return {"status": "ok", "data": row}, 200

    def undo_last_label(self, *, username: str) -> tuple[dict[str, Any], int]:
        """Batalkan label terakhir milik actor -- bekerja lintas reload karena
        disimpan server-side, bukan cuma stack di memori browser."""
        event = self._events.last_event_for_actor(username)
        if not event:
            return {"status": "error", "message": "Tidak ada label untuk dibatalkan."}, 404

        berita_id = event["berita_id"]
        previous = event.get("previous_label")

        row = self._berita.set_human_label(
            berita_id, is_relevant=previous, username=username,
            label_source=event.get("label_source") or "targeted",
            note="undo",
        )
        if row is None and previous is not None:
            return {"status": "error", "message": "Gagal membatalkan label."}, 500

        self._events.record(
            berita_id=berita_id,
            previous_label=event.get("new_label"),
            new_label=previous,
            label_source=event.get("label_source") or "targeted",
            note="undo",
            machine_label=event.get("machine_label"),
            machine_score=event.get("machine_score"),
            prompt_version=event.get("prompt_version"),
            actor_username=username,
        )
        return {"status": "ok", "data": {"berita_id": berita_id, "restored_label": previous}}, 200

    def bulk_set_human_label(
        self, *, berita_ids: list[int], is_relevant: bool, username: str,
        label_source: str = "targeted",
    ) -> tuple[dict[str, Any], int]:
        ids = berita_ids[:MAX_BULK_LABEL]
        if not ids:
            return {"status": "error", "message": "Tidak ada ID yang dikirim."}, 400

        updated, failed = self._berita.bulk_set_human_label(
            ids, is_relevant=is_relevant, username=username, label_source=label_source,
        )
        succeeded_ids = [i for i in ids if i not in failed]
        for bid in succeeded_ids:
            self._events.record(
                berita_id=bid, previous_label=None, new_label=is_relevant,
                label_source=label_source, note="bulk",
                machine_label=None, machine_score=None, prompt_version=None,
                actor_username=username,
            )
        return {"status": "ok", "updated": updated, "failed": failed}, 200

    # ── Re-classify ───────────────────────────────────────────────────────────

    def reclassify_one(self, berita_id: int) -> tuple[dict[str, Any], int]:
        if berita_id <= 0:
            return {"status": "error", "message": "ID tidak valid."}, 400
        from services.article_pipeline import reclassify_article

        res = reclassify_article(berita_id)
        if res is None:
            return {"status": "error", "message": "Gagal klasifikasi ulang (classifier tidak tersedia atau gagal)."}, 502
        return {"status": "ok", "data": res}, 200

    def reclassify_bulk(self, *, berita_ids: list[int] | None = None, limit: int = 25) -> tuple[dict[str, Any], int]:
        from services.article_pipeline import reclassify_article

        if berita_ids:
            ids = berita_ids[:25]
        else:
            rows = self._berita.list_unchecked_relevance_rows(limit=limit, max_attempts=10_000)
            ids = [r["id"] for r in rows]

        if not ids:
            return {"status": "ok", "requested": 0, "succeeded": 0, "still_failed": []}, 200

        succeeded = 0
        still_failed: list[int] = []
        for bid in ids:
            if reclassify_article(bid) is not None:
                succeeded += 1
            else:
                still_failed.append(bid)

        return {
            "status": "ok", "requested": len(ids), "succeeded": succeeded, "still_failed": still_failed,
        }, 200

    # ── Sampel audit ──────────────────────────────────────────────────────────

    def draw_audit_sample(self, *, per_band: int, username: str) -> tuple[dict[str, Any], int]:
        batch_key = f"audit-{int(time.time())}"
        batch_id = self._audit.draw_sample(batch_key=batch_key, per_band=per_band, created_by=username)
        if batch_id is None:
            return {"status": "error", "message": "Gagal menarik sampel audit."}, 500

        batch = self._audit.get_open_batch()
        return {
            "status": "ok",
            "batch_key": batch_key,
            "batch_id": batch_id,
            "band_plan": (batch or {}).get("band_plan", {}),
        }, 200

    def audit_sample_status(self) -> tuple[dict[str, Any], int]:
        batch = self._audit.get_open_batch()
        if not batch:
            return {"status": "ok", "batch": None, "progress": None}, 200
        progress = self._audit.batch_progress(batch["id"])
        return {"status": "ok", "batch": batch, "progress": progress}, 200

    # ── Few-shot export ───────────────────────────────────────────────────────

    def export_few_shot(self, limit: int = 20) -> tuple[dict[str, Any], int]:
        """Bangun dari SEMUA label (koreksi + konfirmasi), bukan disagreement
        saja -- dengan 0 disagreement (kasus live saat ini), versi lama
        selalu balas "Belum ada disagreement". Koreksi diseleksi round-robin
        antar band skor supaya false positive skor tinggi (mesin percaya diri
        tapi salah) tidak terkubur oleh urutan skor menaik seperti versi lama."""
        rows = self._berita.list_labeled_rows(limit=1000, include_content=True)
        corrections = [r for r in rows if bool(r.get("human_label")) != bool(r.get("is_relevant"))]
        confirmations = [r for r in rows if bool(r.get("human_label")) == bool(r.get("is_relevant"))]

        band_buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in corrections:
            band = _band_for_score(r.get("relevance_score")) or "b40_59"
            band_buckets[band].append(r)

        picked_corrections: list[dict[str, Any]] = []
        band_idx = 0
        guard = 0
        while len(picked_corrections) < min(limit, len(corrections)) and guard < limit * 20:
            band = _SCORE_BANDS[band_idx % len(_SCORE_BANDS)]
            band_idx += 1
            guard += 1
            if band_buckets[band]:
                picked_corrections.append(band_buckets[band].pop(0))

        remaining = max(0, limit - len(picked_corrections))
        confirmations_by_uncertainty = sorted(
            confirmations, key=lambda r: abs((r.get("relevance_score") or 50) - 50),
        )
        picked_confirmations = confirmations_by_uncertainty[:remaining]

        false_positives = [r for r in picked_corrections if bool(r.get("is_relevant")) and not bool(r.get("human_label"))]
        false_negatives = [r for r in picked_corrections if not bool(r.get("is_relevant")) and bool(r.get("human_label"))]

        def _format_entry(row: dict[str, Any], correction: str) -> str:
            title = (row.get("title") or "").strip()[:120]
            score = row.get("relevance_score", "?")
            reason = (row.get("relevance_reason") or "").strip()[:200]
            snippet = (row.get("content") or "").strip()[:120].replace("\n", " ")
            lines = [f'- "{title}"', f"  Skor mesin: {score} → Koreksi: {correction}"]
            if reason:
                lines.append(f'  Alasan mesin: "{reason}"')
            if snippet:
                lines.append(f'  Konteks: "{snippet}..."')
            return "\n".join(lines)

        def _format_confirmation(row: dict[str, Any]) -> str:
            title = (row.get("title") or "").strip()[:120]
            score = row.get("relevance_score", "?")
            verdict = "RELEVAN" if row.get("is_relevant") else "TIDAK RELEVAN"
            reason = (row.get("relevance_reason") or "").strip()[:200]
            lines = [f'- "{title}"', f"  Skor mesin: {score} → Dikonfirmasi manusia: {verdict}"]
            if reason:
                lines.append(f'  Alasan mesin: "{reason}"')
            return "\n".join(lines)

        fp_blocks = [_format_entry(r, "TIDAK RELEVAN") for r in false_positives]
        fn_blocks = [_format_entry(r, "RELEVAN") for r in false_negatives]
        confirm_blocks = [_format_confirmation(r) for r in picked_confirmations]

        sections: list[str] = [
            "=== MENU KURASI FEW-SHOT UNTUK SYSTEM_PROMPT ===",
            f"Total label manusia: {len(rows)} (koreksi={len(corrections)}, konfirmasi={len(confirmations)})",
            "",
        ]

        if not corrections:
            sections.append(
                "Belum ada koreksi — mesin sepakat dengan semua label manusia yang ada. "
                "Contoh di bawah adalah konfirmasi kasus sulit; pakai untuk mempertegas "
                "rubrik, bukan membalik keputusan."
            )
            sections.append("")

        if fp_blocks:
            sections.append("--- Contoh TIDAK RELEVAN (mesin salah: bilang relevan) ---")
            sections.extend(fp_blocks)
            sections.append("")

        if fn_blocks:
            sections.append("--- Contoh RELEVAN (mesin salah: bilang tidak relevan) ---")
            sections.extend(fn_blocks)
            sections.append("")

        if confirm_blocks:
            sections.append("--- Konfirmasi kasus sulit (mesin sudah benar, skor dekat ambang) ---")
            sections.extend(confirm_blocks)
            sections.append("")

        formatted_prompt = "\n".join(sections)

        return {
            "status": "ok",
            "total_labels": len(rows),
            "corrections": {
                "false_positives": [_export_row(r) for r in false_positives],
                "false_negatives": [_export_row(r) for r in false_negatives],
            },
            "confirmations": [_export_row(r) for r in picked_confirmations],
            "formatted_prompt": formatted_prompt,
        }, 200

    # ── Metrik ────────────────────────────────────────────────────────────────

    def metrics(self, *, prompt_version: str | None = None) -> tuple[dict[str, Any], int]:
        all_rows = self._berita.relevance_confusion_rows(prompt_version=prompt_version)
        sample_block = _confusion_block(all_rows)

        audit_rows = self._berita.relevance_confusion_rows(label_source="audit", prompt_version=prompt_version)
        audit_labels = len(audit_rows)
        audit_block = None
        if audit_labels >= MIN_AUDIT_LABELS_FOR_METRICS:
            band_population = self._berita.count_scored_by_band()
            audit_block = _weighted_confusion_block(audit_rows, band_population)

        targeted_labels = len(all_rows) - audit_labels
        bias_warning = None
        if audit_labels == 0:
            bias_warning = (
                "Semua label berasal dari antrean terarah (borderline/uncertainty). "
                "Angka precision/recall di atas TIDAK mewakili performa di seluruh korpus. "
                "Tarik sampel audit acak untuk mendapat estimasi tak bias."
            )
        elif audit_labels < MIN_AUDIT_LABELS_FOR_METRICS:
            bias_warning = (
                f"Baru {audit_labels} label audit (butuh {MIN_AUDIT_LABELS_FOR_METRICS}) -- "
                "blok tak bias di bawah belum ditampilkan."
            )

        return {
            "status": "ok",
            "sample": sample_block,
            "audit": audit_block,
            "bias": {
                "audit_labels": audit_labels,
                "targeted_labels": targeted_labels,
                "audit_share": (audit_labels / len(all_rows)) if all_rows else 0.0,
                "warning": bias_warning,
            },
            "per_prompt_version": _metrics_by_version(all_rows),
        }, 200
