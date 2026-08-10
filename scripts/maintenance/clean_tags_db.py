"""
scripts.maintenance.clean_tags_db — Bersihkan tag existing di database

Menerapkan clean_tags() (utils/tags.py) pada semua artikel yang memiliki tag:
menghapus nama daerah, identitas sumber media, nama pejabat, stop word, dan
tag terlalu pendek.

DEFAULT = DRY-RUN. Script ini HANYA membuat laporan kecuali diberi --apply.
Ini destruktif (menimpa berita.tags) dan tidak bisa "dicoba dulu" tanpa
--dry-run terpisah — makanya arahnya dibalik: harus eksplisit minta menulis.

Cara pakai:
    python -m scripts.maintenance.clean_tags_db                       # laporan ringkas
    python -m scripts.maintenance.clean_tags_db --report removed --top 60
    python -m scripts.maintenance.clean_tags_db --report persons --top 100
    python -m scripts.maintenance.clean_tags_db --out data/tag_preview.csv
    python -m scripts.maintenance.clean_tags_db --apply --snapshot        # tulis (konfirmasi ketik)
    python -m scripts.maintenance.clean_tags_db --apply --snapshot --yes  # tulis (non-interaktif)
    python -m scripts.maintenance.clean_tags_db --restore                # kembalikan dari snapshot
"""

import argparse
import csv
import os
import sys
import time
from dataclasses import dataclass, field

from dotenv import load_dotenv
from supabase import create_client

from utils.tags import DROP_REASONS, inspect_tags

load_dotenv()

_FETCH_BATCH = 500  # ambil sekaligus, kurangi round-trips
_APPLY_CONFIRMATION = "hapus tag"

# Kata yang menandakan tag adalah nama BADAN USAHA/institusi, bukan orang —
# dipakai --report persons untuk menghindari menyarankan "Pupuk Indonesia"
# sebagai kandidat nama pejabat. Murni penyaring saran, tidak pernah
# menghapus apa pun sendiri.
_ORG_HINT_WORDS = frozenset({
    "pt", "cv", "tbk", "persero", "group", "grup", "industri", "chemical",
    "mall", "bank", "koperasi", "kawasan", "pasar", "desa", "kecamatan",
    "kabupaten", "kota", "dinas", "badan", "kantor", "yayasan", "perusahaan",
    "pabrik", "toko", "warung", "klinik", "rumah", "sakit", "sekolah",
    "universitas", "asosiasi", "komunitas", "forum", "klub", "indonesia",
    "nasional", "daerah", "wilayah", "polres", "polsek", "koramil", "kodim",
})


@dataclass
class ReportData:
    total_rows: int = 0
    changed_rows: int = 0
    tags_before_unique: set = field(default_factory=set)
    tags_after_unique: set = field(default_factory=set)
    reason_unique: dict = field(default_factory=lambda: {r: set() for r in DROP_REASONS})
    reason_occurrences: dict = field(default_factory=lambda: dict.fromkeys(DROP_REASONS, 0))
    removed_tag_counts: dict = field(default_factory=dict)  # (tag_lower, reason) -> count
    kept_tag_counts: dict = field(default_factory=dict)     # tag_lower -> count
    rows_losing_all_tags: list = field(default_factory=list)
    diffs: list = field(default_factory=list)  # [{id, tags_before, tags_after, rules_hit}]


def _get_supabase():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        print("[CleanTags] ERROR: SUPABASE_URL atau SUPABASE_KEY tidak ditemukan.")
        sys.exit(1)
    return create_client(url, key)


def _fetch_tagged_rows(supabase, limit: int = 0) -> list[dict]:
    print("[CleanTags] Mengambil data tag dari database...")
    all_rows: list[dict] = []
    offset = 0
    while True:
        res = (
            supabase.table("berita")
            .select("id, tags")
            .not_.is_("tags", "null")
            .order("id")
            .range(offset, offset + _FETCH_BATCH - 1)
            .execute()
        )
        batch = res.data or []
        if not batch:
            break
        all_rows.extend(batch)
        offset += _FETCH_BATCH
        if len(batch) < _FETCH_BATCH:
            break
        if limit and len(all_rows) >= limit:
            break
    if limit:
        all_rows = all_rows[:limit]
    return all_rows


def compute_report(rows: list[dict]) -> ReportData:
    """Satu jalur analisis dipakai laporan DAN --apply, jadi keduanya tidak
    mungkin berbeda hasil (inspect_tags adalah satu-satunya sumber kebenaran)."""
    report = ReportData(total_rows=len(rows))

    for row in rows:
        raw = row.get("tags") or ""
        if not raw:
            continue

        pairs = inspect_tags(raw)
        kept_tags = [tag for tag, reason in pairs if reason is None]
        cleaned = " | ".join(kept_tags)

        for tag, reason in pairs:
            lowered = tag.lower()
            report.tags_before_unique.add(lowered)
            if reason is None:
                report.tags_after_unique.add(lowered)
                report.kept_tag_counts[lowered] = report.kept_tag_counts.get(lowered, 0) + 1
            else:
                report.reason_unique[reason].add(lowered)
                report.reason_occurrences[reason] += 1
                key = (lowered, reason)
                report.removed_tag_counts[key] = report.removed_tag_counts.get(key, 0) + 1

        if cleaned != raw:
            report.changed_rows += 1
            rules_hit = sorted({reason for _tag, reason in pairs if reason})
            report.diffs.append({
                "id": row["id"],
                "tags_before": raw,
                "tags_after": cleaned,
                "rules_hit": ",".join(rules_hit),
            })
            if not cleaned and raw.strip():
                report.rows_losing_all_tags.append(row["id"])

    return report


def _looks_like_person_name(tag: str) -> bool:
    """Heuristik SARAN, bukan aturan penghapus. 2-3 kata alfabetis, tidak ada
    kata petunjuk organisasi. Dipakai --report persons untuk membantu manusia
    menemukan kandidat OFFICIAL_PERSON_TAGS baru — tidak pernah menghapus apa
    pun sendiri."""
    words = tag.split()
    if not (2 <= len(words) <= 3):
        return False
    if not all(w.isalpha() for w in words):
        return False
    if any(w.lower() in _ORG_HINT_WORDS for w in words):
        return False
    return True


def print_summary_report(report: ReportData, *, dry_run: bool) -> None:
    if dry_run:
        print("[CleanTags] DRY-RUN — tidak ada perubahan ditulis. Tambahkan --apply untuk menerapkan.\n")

    pct = (report.changed_rows / report.total_rows * 100) if report.total_rows else 0
    removed_unique = len(report.tags_before_unique) - len(report.tags_after_unique)
    removed_occurrences = sum(report.reason_occurrences.values())

    print(f"  Artikel bertag            : {report.total_rows}")
    print(f"  Artikel akan berubah      : {report.changed_rows}  ({pct:.1f}%)")
    print(
        f"  Tag unik sebelum / sesudah: {len(report.tags_before_unique)} -> "
        f"{len(report.tags_after_unique)}   (dibuang {removed_unique} unik / "
        f"{removed_occurrences} kemunculan)"
    )
    print()
    print("  Dibuang per aturan          unik   kemunculan")
    for reason in DROP_REASONS:
        print(f"    {reason:<20} {len(report.reason_unique[reason]):>8} {report.reason_occurrences[reason]:>12}")

    if report.rows_losing_all_tags:
        ids = report.rows_losing_all_tags[:10]
        suffix = ", ..." if len(report.rows_losing_all_tags) > 10 else ""
        print()
        print(f"  !! {len(report.rows_losing_all_tags)} artikel akan kehilangan SELURUH tag-nya "
              f"(id: {', '.join(str(i) for i in ids)}{suffix})")
        print("     Periksa beberapa sebelum --apply.")


def print_removed_report(report: ReportData, *, top: int) -> None:
    print_summary_report(report, dry_run=True)
    ranked = sorted(report.removed_tag_counts.items(), key=lambda kv: kv[1], reverse=True)[:top]
    print(f"\n  {len(ranked)} tag paling sering dibuang")
    for (tag, reason), count in ranked:
        print(f"    {count:>5}x  {tag:<28} [{reason}]")


def print_persons_report(report: ReportData, *, top: int) -> None:
    candidates = [
        (tag, count) for tag, count in report.kept_tag_counts.items()
        if _looks_like_person_name(tag)
    ]
    candidates.sort(key=lambda kv: kv[1], reverse=True)
    candidates = candidates[:top]

    print(f"[CleanTags] {len(candidates)} kandidat nama pejabat (tag YANG MASIH LOLOS, belum di-blocklist).")
    print("  Ini SARAN, bukan keputusan — periksa mata, lalu tambahkan manual ke")
    print("  config.region.OFFICIAL_PERSON_TAGS bila memang nama pejabat.\n")
    for tag, count in candidates:
        print(f"    {count:>5}x  {tag}")


def write_csv(report: ReportData, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "tags_before", "tags_after", "rules_hit"])
        writer.writeheader()
        writer.writerows(report.diffs)
    print(f"[CleanTags] Pratinjau ditulis ke {path} ({len(report.diffs)} baris berubah).")


def apply_changes(supabase, report: ReportData, *, snapshot: bool, yes: bool) -> None:
    if not report.diffs:
        print("[CleanTags] Tidak ada yang perlu diupdate.")
        return

    print_summary_report(report, dry_run=False)

    if not yes:
        print(f"\nKetik '{_APPLY_CONFIRMATION}' untuk melanjutkan, atau apa saja lain untuk batal: ", end="")
        typed = input().strip()
        if typed != _APPLY_CONFIRMATION:
            print("[CleanTags] Dibatalkan.")
            return

    if snapshot:
        print("[CleanTags] Menyimpan snapshot ke tag_cleanup_backup...")
        for i, diff in enumerate(report.diffs, 1):
            try:
                supabase.table("tag_cleanup_backup").upsert({
                    "berita_id":   diff["id"],
                    "tags_before": diff["tags_before"],
                    "tags_after":  diff["tags_after"],
                    "rules_hit":   diff["rules_hit"],
                }).execute()
            except Exception as exc:
                print(f"[CleanTags] Gagal snapshot id={diff['id']}: {exc}")
                print("[CleanTags] Dihentikan — perbaiki migrasi tag_cleanup_backup lalu ulangi.")
                sys.exit(1)
            if i % 200 == 0:
                print(f"[CleanTags] Snapshot {i}/{len(report.diffs)}...")

    updated = 0
    failed = 0
    start_time = time.time()

    for i, diff in enumerate(report.diffs, 1):
        try:
            supabase.table("berita").update({"tags": diff["tags_after"]}).eq("id", diff["id"]).execute()
            updated += 1
        except Exception as exc:
            print(f"[CleanTags] Gagal update id={diff['id']}: {exc}")
            failed += 1

        if i % 50 == 0 or i == len(report.diffs):
            elapsed = time.time() - start_time
            print(f"[CleanTags] {i}/{len(report.diffs)} diupdate | Waktu: {elapsed:.1f}s")

    elapsed_total = time.time() - start_time
    print()
    print("=" * 60)
    print("[CleanTags] SELESAI")
    print(f"  Total artikel   : {report.total_rows}")
    print(f"  Tag diperbarui  : {updated} artikel")
    print(f"  Gagal           : {failed} artikel")
    print(f"  Total waktu     : {elapsed_total:.1f} detik")
    if snapshot:
        print("  Snapshot        : tag_cleanup_backup (pakai --restore untuk kembalikan)")
    print("=" * 60)


def restore(supabase) -> None:
    print("[CleanTags] Mengambil snapshot dari tag_cleanup_backup...")
    all_rows: list[dict] = []
    offset = 0
    while True:
        res = (
            supabase.table("tag_cleanup_backup")
            .select("berita_id, tags_before")
            .order("berita_id")
            .range(offset, offset + _FETCH_BATCH - 1)
            .execute()
        )
        batch = res.data or []
        if not batch:
            break
        all_rows.extend(batch)
        offset += _FETCH_BATCH
        if len(batch) < _FETCH_BATCH:
            break

    if not all_rows:
        print("[CleanTags] Tabel tag_cleanup_backup kosong — tidak ada yang dikembalikan.")
        return

    print(f"[CleanTags] Mengembalikan {len(all_rows)} baris ke tag semula...")
    restored = 0
    failed = 0
    for row in all_rows:
        try:
            supabase.table("berita").update(
                {"tags": row["tags_before"]}
            ).eq("id", row["berita_id"]).execute()
            restored += 1
        except Exception as exc:
            print(f"[CleanTags] Gagal restore id={row['berita_id']}: {exc}")
            failed += 1

    print(f"[CleanTags] Selesai — {restored} dikembalikan, {failed} gagal. "
          f"Tabel tag_cleanup_backup TIDAK dihapus otomatis.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="clean_tags_db",
        description="Pratinjau & terapkan utils.tags.clean_tags ke seluruh kolom berita.tags.",
    )
    p.add_argument("--apply", action="store_true",
                    help="Tulis perubahan. Tanpa flag ini script HANYA membuat laporan.")
    p.add_argument("--snapshot", action="store_true",
                    help="Simpan tag asli ke tag_cleanup_backup sebelum menimpa. Sangat disarankan bersama --apply.")
    p.add_argument("--restore", action="store_true",
                    help="Kembalikan tags dari tag_cleanup_backup lalu keluar.")
    p.add_argument("--yes", action="store_true", help="Lewati konfirmasi interaktif.")
    p.add_argument("--report", choices=("summary", "removed", "persons"), default="summary")
    p.add_argument("--top", type=int, default=40, help="Jumlah contoh pada laporan.")
    p.add_argument("--limit", type=int, default=0, help="Batasi baris diproses (0 = semua).")
    p.add_argument("--out", default="", help="Tulis laporan diff ke CSV di path ini.")
    return p


def main() -> None:
    args = build_parser().parse_args()
    supabase = _get_supabase()

    if args.restore:
        restore(supabase)
        return

    rows = _fetch_tagged_rows(supabase, limit=args.limit)
    print(f"[CleanTags] {len(rows)} artikel memiliki tag — menganalisis...")
    report = compute_report(rows)

    if args.out:
        write_csv(report, args.out)

    if args.apply:
        apply_changes(supabase, report, snapshot=args.snapshot, yes=args.yes)
        return

    if args.report == "removed":
        print_removed_report(report, top=args.top)
    elif args.report == "persons":
        print_persons_report(report, top=args.top)
    else:
        print_summary_report(report, dry_run=True)


if __name__ == "__main__":
    main()
