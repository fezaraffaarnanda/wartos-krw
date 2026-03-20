"""
Utils untuk normalisasi tanggal dan pembersihan tag.

- normalize_date()    : "DD MMMM YYYY, HH:MM WIB"
- parse_date_to_iso() : "YYYY-MM-DD"
- clean_tags()        : hapus tag tidak informatif (nama daerah, stop words, dll.)
"""

import re

# ── Blocklist tag tidak informatif ─────────────────────────────────────────────

# 1. Stop words — exact match (seluruh tag, case-insensitive)
#    "hari raya" TIDAK dihapus; "hari" saja yang dihapus.
_STOPWORD_EXACT: frozenset[str] = frozenset({
    "ini", "itu", "dan", "di", "ke", "dari", "yang", "untuk",
    "dengan", "ada", "bisa", "juga", "sudah", "akan", "lagi",
    "oleh", "atau", "saja", "pun", "bila", "jika", "ia", "si",
    "hari", "bulan", "tahun", "orang", "pada", "hal", "cara",
    "bagi", "agar", "saat", "serta", "lebih", "belum", "masih",
    "kami", "kamu", "anda", "kita", "mereka", "dia", "nya",
    "berita", "terbaru", "update",
})

# 2. Kata-kata lokasi — word-boundary match (menangkap compound: "berita tegal", "pemkab tegal", dll.)
#    Pola ini mencocokkan tag yang *mengandung* kata lokasi sebagai kata utuh.
#    Contoh: "berita tegal hari ini"  → mengandung \btegal\b  → DIHAPUS
#            "berita tegal"           → mengandung \btegal\b  → DIHAPUS
#            "pemkab tegal"           → mengandung \btegal\b  → DIHAPUS
#            "pertanian"              → tidak ada kata lokasi  → LOLOS
_RE_LOCATION = re.compile(
    r"\b(?:tegal|kota tegal|kabupaten tegal|slawi|jawa tengah|jateng"
    r"|brebes|pemalang|pekalongan|batang|kendal|pemkab|pemkot)\b",
    re.IGNORECASE,
)

# 3. Regex cepat untuk tag yang hanya angka atau ≤ 2 karakter
_RE_TAG_TRIVIAL = re.compile(r"^\d+$|^.{1,2}$")

BULAN_NUM = {
    "januari": "01", "februari": "02", "maret": "03",
    "april": "04", "mei": "05", "juni": "06",
    "juli": "07", "agustus": "08", "september": "09",
    "oktober": "10", "november": "11", "desember": "12",
}

BULAN_NAMA = {v: k.capitalize() for k, v in BULAN_NUM.items()}


def _num_to_nama(month_num: str) -> str:
    return BULAN_NAMA.get(month_num.zfill(2), month_num)


def _nama_to_num(month_str: str) -> str:
    return BULAN_NUM.get(month_str.lower().strip(), "01")


def normalize_date(raw: str) -> str:
    """
    Normalisasi berbagai format tanggal ke "DD MMMM YYYY, HH:MM WIB".

    Format yang didukung:
      RadarTegal  : "Senin 23-02-2026,16:04 WIB"
      PanturaPost : "- Sabtu, 28 Februari 2026 | 21:32 WIB"
      TribunJateng: "Kamis, 5 Februari 2026 15:31 WIB"
    """
    if not raw:
        return raw

    raw = raw.strip()

    # ── RadarTegal: "Senin 23-02-2026,16:04 WIB" ──────────────────────────────
    m = re.search(r"(\d{2})-(\d{2})-(\d{4})[,\s]+(\d{2}:\d{2})", raw)
    if m:
        day, month_num, year, time = m.group(1), m.group(2), m.group(3), m.group(4)
        return f"{int(day)} {_num_to_nama(month_num)} {year}, {time} WIB"

    # ── PanturaPost: "- Sabtu, 28 Februari 2026 | 21:32 WIB" ──────────────────
    m = re.search(
        r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\s*[|\s]+(\d{2}:\d{2})",
        raw,
    )
    if m:
        day, month_str, year, time = m.group(1), m.group(2), m.group(3), m.group(4)
        return f"{int(day)} {month_str.capitalize()} {year}, {time} WIB"

    # ── Kompas: "Kamis, 6 Maret 2026, 10:55 WIB" ──────────────────────────────
    m = re.search(
        r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4}),\s*(\d{2}:\d{2})",
        raw,
    )
    if m:
        day, month_str, year, time = m.group(1), m.group(2), m.group(3), m.group(4)
        return f"{int(day)} {month_str.capitalize()} {year}, {time} WIB"

    # ── TribunJateng: "Kamis, 5 Februari 2026 15:31 WIB" ─────────────────────
    m = re.search(
        r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\s+(\d{2}:\d{2})",
        raw,
    )
    if m:
        day, month_str, year, time = m.group(1), m.group(2), m.group(3), m.group(4)
        return f"{int(day)} {month_str.capitalize()} {year}, {time} WIB"

    # fallback: kembalikan apa adanya
    return raw


def parse_date_to_iso(normalized: str) -> str | None:
    """
    Ubah hasil normalize_date ("DD MMMM YYYY, HH:MM WIB") ke "YYYY-MM-DD".
    Return None jika tidak bisa di-parse.
    Contoh: "7 Maret 2026, 14:30 WIB"  →  "2026-03-07"
    """
    if not normalized:
        return None
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", normalized)
    if not m:
        return None
    day, month_str, year = m.group(1), m.group(2), m.group(3)
    month_num = BULAN_NUM.get(month_str.lower())
    if not month_num:
        return None
    return f"{year}-{month_num}-{int(day):02d}"


# ── Tag cleaning ───────────────────────────────────────────────────────────────

def clean_tags(raw: str | None) -> str:
    """
    Bersihkan string tag berita dari entri yang tidak informatif.

    Menghapus:
    - Tag ≤ 2 karakter atau hanya angka
    - Tag yang MENGANDUNG kata lokasi (tegal, slawi, brebes, dll.) sebagai kata utuh
      → menangkap compound: "berita tegal", "pemkab tegal", "berita tegal hari ini"
    - Stop words (exact match): "hari", "ini", "dan", dll.
    - Duplikat (case-insensitive)

    Input  : string tag mentah, separator " | " atau ", " (atau campur)
    Output : string tag bersih dengan separator " | "

    Contoh:
        "berita tegal | perekonomian | ini | UMKM" → "perekonomian | UMKM"
        "pemkab tegal, hari, pertanian"            → "pertanian"
        "berita tegal hari ini, infrastruktur"     → "infrastruktur"
    """
    if not raw:
        return ""

    parts = re.split(r"\s*\|\s*|,\s*", raw)

    seen:   set[str]  = set()
    result: list[str] = []

    for part in parts:
        tag = part.strip().lstrip("#").strip()
        if not tag:
            continue
        # Filter 1: angka atau terlalu pendek
        if _RE_TAG_TRIVIAL.match(tag):
            continue
        # Filter 2: mengandung kata lokasi (word-boundary)
        if _RE_LOCATION.search(tag):
            continue
        # Filter 3: stop words (exact)
        if tag.lower() in _STOPWORD_EXACT:
            continue
        # Deduplication (case-insensitive)
        lower = tag.lower()
        if lower in seen:
            continue
        seen.add(lower)
        result.append(tag)

    return " | ".join(result)
