"""
Utilitas pembersihan tag berita.
"""

import re

_STOPWORD_EXACT: frozenset[str] = frozenset({
    "ini", "itu", "dan", "di", "ke", "dari", "yang", "untuk",
    "dengan", "ada", "bisa", "juga", "sudah", "akan", "lagi",
    "oleh", "atau", "saja", "pun", "bila", "jika", "ia", "si",
    "hari", "bulan", "tahun", "orang", "pada", "hal", "cara",
    "bagi", "agar", "saat", "serta", "lebih", "belum", "masih",
    "kami", "kamu", "anda", "kita", "mereka", "dia", "nya",
    "berita", "terbaru", "update",
})

_RE_LOCATION = re.compile(
    r"\b(?:tegal|kota tegal|kabupaten tegal|slawi|jawa tengah|jateng"
    r"|brebes|pemalang|pekalongan|batang|kendal|pemkab|pemkot"
    r"|karawang|cikampek|purwakarta|jawa barat|jabar|bekasi"
    r"|telukjambe|rengasdengklok|cilamaya|klari|kotabaru"
    r"|pemda|pemprov|jakarta|indonesia|nasional)\b",
    re.IGNORECASE,
)

_RE_TAG_TRIVIAL = re.compile(r"^\d+$|^.{1,2}$")


def clean_tags(raw: str | None) -> str:
    """
    Bersihkan string tag berita dari entri yang tidak informatif.
    """
    if not raw:
        return ""

    parts = re.split(r"\s*\|\s*|,\s*", raw)

    seen: set[str] = set()
    result: list[str] = []

    for part in parts:
        tag = part.strip().lstrip("#").strip()
        if not tag:
            continue
        if _RE_TAG_TRIVIAL.match(tag):
            continue
        if _RE_LOCATION.search(tag):
            continue
        if tag.lower() in _STOPWORD_EXACT:
            continue

        lower = tag.lower()
        if lower in seen:
            continue

        seen.add(lower)
        result.append(tag)

    return " | ".join(result)
