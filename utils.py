"""
Utilitas normalisasi tanggal dari berbagai format portal berita.

Target format: "DD MMMM YYYY, HH:MM WIB"
Contoh: "23 Februari 2026, 16:04 WIB"
"""

import re

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
