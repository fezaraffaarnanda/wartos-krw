"""Ukur mutu jawaban AI Chat terhadap set pertanyaan acuan.

Dijalankan manual -- memakai kuota LLM sungguhan, jadi bukan bagian pytest:

    python scripts/eval_chat.py                 # seluruh kasus
    python scripts/eval_chat.py --id wilayah    # kasus yang id-nya memuat "wilayah"
    python scripts/eval_chat.py --out hasil.json

Yang diperiksa per kasus:
  must_contain     - semua substring wajib muncul di jawaban
  must_not_contain - satu pun muncul berarti gagal
  must_cite        - "statistik" | "berita" | "any" | "none"

Gunanya membandingkan sebelum/sesudah perubahan prompt atau retrieval. Angka
acuan di fixture berasal dari sumber resmi yang sudah dipakai aplikasi, jadi
kegagalan berarti jawaban menyimpang dari data yang sebenarnya dikirim.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.chat import generate_rag_answer  # noqa: E402
from clients.supabase import supabase  # noqa: E402

_QUESTIONS_PATH = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "chat_eval" / "questions.json"


def _load_cases(needle: str = "") -> list[dict]:
    cases = json.loads(_QUESTIONS_PATH.read_text(encoding="utf-8"))
    if needle:
        cases = [case for case in cases if needle.lower() in case["id"].lower()]
    return cases


def _check_citations(expectation: str, citations: list[dict]) -> tuple[bool, str]:
    kinds = {str(c.get("type") or "berita") for c in citations}
    if expectation == "none":
        return (not citations, "ada sitasi padahal tidak diharapkan")
    if expectation == "any":
        return (bool(citations), "tidak ada sitasi sama sekali")
    return (expectation in kinds, f"tidak ada sitasi bertipe {expectation}")


def _evaluate(case: dict, answer: str, citations: list[dict]) -> list[str]:
    """Kembalikan daftar pelanggaran; kosong berarti lolos."""
    failures: list[str] = []
    lowered = answer.lower()

    for needle in case.get("must_contain", []):
        if needle.lower() not in lowered:
            failures.append(f"tidak memuat {needle!r}")

    for needle in case.get("must_not_contain", []):
        if needle.lower() in lowered:
            failures.append(f"memuat {needle!r} yang dilarang")

    expectation = case.get("must_cite")
    if expectation:
        ok, message = _check_citations(expectation, citations)
        if not ok:
            failures.append(message)

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Eval mutu jawaban AI Chat.")
    parser.add_argument("--id", default="", help="jalankan hanya kasus yang id-nya memuat teks ini")
    parser.add_argument("--out", default="", help="tulis hasil lengkap ke berkas JSON")
    args = parser.parse_args()

    cases = _load_cases(args.id)
    if not cases:
        print("Tidak ada kasus yang cocok.")
        return 1

    results: list[dict] = []
    passed = 0

    for idx, case in enumerate(cases, 1):
        t0 = perf_counter()
        try:
            payload = generate_rag_answer(
                query=case["question"], supabase_client=supabase, history=[],
            )
            answer = str(payload.get("answer") or "")
            citations = payload.get("citations") or []
            error = ""
        except Exception as exc:  # noqa: BLE001 - laporan eval, bukan jalur produksi
            answer, citations, error = "", [], str(exc)

        elapsed_ms = (perf_counter() - t0) * 1000
        failures = [f"gagal memanggil chat: {error}"] if error else _evaluate(case, answer, citations)
        if not failures:
            passed += 1

        status = "LULUS" if not failures else "GAGAL"
        print(f"[{idx:2d}/{len(cases)}] {status}  {case['id']}  ({elapsed_ms:.0f} ms)")
        for failure in failures:
            print(f"           - {failure}")

        results.append({
            "id": case["id"],
            "question": case["question"],
            "answer": answer,
            "citations": citations,
            "failures": failures,
            "latency_ms": round(elapsed_ms, 1),
        })

    print(f"\nSkor: {passed}/{len(cases)} lulus")

    if args.out:
        Path(args.out).write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        print(f"Hasil lengkap ditulis ke {args.out}")

    return 0 if passed == len(cases) else 2


if __name__ == "__main__":
    raise SystemExit(main())
