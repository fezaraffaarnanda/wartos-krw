"""
Utilitas pembersihan tag berita.

SATU-SATUNYA tempat aturan pembersihan tag hidup. Jangan menduplikasi aturan
ini ke JavaScript — frontend hanya memisah string (lihat
static/js/shared/tags.js::parseTags).
"""

import re

from config.region import (
    NEWS_SOURCE_IDENTITY_TAGS,
    OFFICIAL_PERSON_TAGS,
    PERSON_TITLE_TOKENS,
)

# ── Normalisasi ─────────────────────────────────────────────────────────────

_RE_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_RE_WS = re.compile(r"\s+")

# NB: setiap tag individual sudah lolos split_tags() sebelum sampai di sini,
# dan split_tags membelah pada koma juga — jadi satu tag TIDAK PERNAH
# mengandung koma (mis. "Aep Syaepuloh, S.H." sudah jadi dua tag terpisah
# sebelum fungsi ini dipanggil). Gelar berkode titik tanpa koma di depannya
# (mis. "H." di awal) tetap tertangkap lewat PERSON_TITLE_TOKENS.
_TITLE_ALTERNATION = "|".join(
    re.escape(t) for t in sorted(PERSON_TITLE_TOKENS, key=len, reverse=True)
)
_RE_TITLE_STRIP = re.compile(
    rf"^(?:(?:{_TITLE_ALTERNATION})\s+)+|(?:\s+(?:{_TITLE_ALTERNATION}))+$"
)


def _squash(text: str) -> str:
    """'Radar-Karawang' / 'radar karawang' / 'RadarKarawang' -> 'radarkarawang'."""
    return _RE_NON_ALNUM.sub("", text.lower())


def _strip_titles(text: str) -> str:
    """'Bupati H. Aep Syaepuloh' -> 'aep syaepuloh'."""
    spaced = _RE_WS.sub(" ", _RE_NON_ALNUM.sub(" ", text.lower())).strip()
    previous = None
    while previous != spaced:  # gelar bisa bertumpuk ("Bupati H. ...")
        previous = spaced
        spaced = _RE_TITLE_STRIP.sub("", spaced).strip()
    return spaced


# ── Kamus aturan ────────────────────────────────────────────────────────────

_STOPWORD_EXACT: frozenset[str] = frozenset({
    "ini", "itu", "dan", "di", "ke", "dari", "yang", "untuk",
    "dengan", "ada", "bisa", "juga", "sudah", "akan", "lagi",
    "oleh", "atau", "saja", "pun", "bila", "jika", "ia", "si",
    "hari", "bulan", "tahun", "orang", "pada", "hal", "cara",
    "bagi", "agar", "saat", "serta", "lebih", "belum", "masih",
    "kami", "kamu", "anda", "kita", "mereka", "dia", "nya",
    "berita", "terbaru", "update",
})

_SOURCE_IDENTITY: frozenset[str] = frozenset(
    _squash(item) for item in NEWS_SOURCE_IDENTITY_TAGS
)

_PERSON_NAMES: frozenset[str] = frozenset(
    _squash(_strip_titles(item)) for item in OFFICIAL_PERSON_TAGS
)

# URL / handle / domain apa pun — menangkap identitas sumber yang tidak
# terdaftar eksplisit tanpa perlu tahu nama medianya.
_RE_SOURCE_DOMAIN = re.compile(
    r"https?://|www\."                        # url
    r"|\.(?:com|co\.id|id|net|org|news|tv)\b"  # tld
    r"|^@",                                    # handle sosial
    re.IGNORECASE,
)


# Nama tempat spesifik — aman dicocokkan sebagai substring karena jarang
# muncul di dalam nama entitas lain.
_RE_LOCATION = re.compile(
    r"\b(?:tegal|kota tegal|kabupaten tegal|slawi|jawa tengah|jateng"
    r"|brebes|pemalang|pekalongan|batang|kendal"
    r"|karawang|cikampek|purwakarta|jawa barat|jabar|bekasi"
    r"|telukjambe|rengasdengklok|cilamaya|klari|kotabaru)\b",
    re.IGNORECASE,
)

# Kata cakupan generik (bukan nama tempat spesifik) — SERING muncul di dalam
# nama entitas sah ("Pupuk Indonesia", "Bank Indonesia", "Pos Indonesia").
# Karena itu hanya dianggap tag lokasi kalau itu SELURUH isi tag, bukan
# dicocokkan sebagai substring seperti _RE_LOCATION di atas.
_GENERIC_SCOPE_EXACT: frozenset[str] = frozenset({
    "indonesia", "nasional", "jakarta", "pemda", "pemprov", "pemkab", "pemkot",
})

_RE_TAG_TRIVIAL = re.compile(r"^\d+$|^.{1,2}$")

DROP_REASONS: tuple[str, ...] = (
    "trivial", "stopword", "sumber", "pejabat", "lokasi", "duplikat",
)


# ── Inti ────────────────────────────────────────────────────────────────────

def split_tags(raw: str | None) -> list[str]:
    """Pisah string tag jadi list, tanpa penyaringan. Pemisah tunggal se-app."""
    if not raw:
        return []
    return [
        part.strip().lstrip("#").strip()
        for part in re.split(r"\s*\|\s*|,\s*", raw)
        if part.strip().lstrip("#").strip()
    ]


def _drop_reason(tag: str) -> str | None:
    """Alasan tag dibuang, atau None kalau dipertahankan.

    Urutan murni soal biaya (regex termurah dulu), bukan kebenaran: semua
    aturan bersifat buang-atau-simpan (tidak ada yang menulis ulang tag),
    jadi hasil akhirnya identik untuk urutan mana pun.
    """
    if _RE_TAG_TRIVIAL.match(tag):
        return "trivial"

    lowered = tag.lower()
    if lowered in _STOPWORD_EXACT:
        return "stopword"

    squashed = _squash(tag)
    if squashed in _SOURCE_IDENTITY or _RE_SOURCE_DOMAIN.search(tag):
        return "sumber"

    if _squash(_strip_titles(tag)) in _PERSON_NAMES:
        return "pejabat"

    if lowered.strip() in _GENERIC_SCOPE_EXACT:
        return "lokasi"

    # NB: dicek pada tag ASLI, bukan bentuk ternormalisasi, agar perilaku
    # lama (substring match) tidak berubah diam-diam.
    if _RE_LOCATION.search(tag):
        return "lokasi"

    return None


def inspect_tags(raw: str | None) -> list[tuple[str, str | None]]:
    """[(tag, alasan_dibuang | None), ...] — dipakai clean_tags DAN laporan CLI.

    Satu implementasi untuk keduanya supaya laporan pratinjau tidak mungkin
    berbeda dari yang benar-benar dieksekusi.
    """
    seen: set[str] = set()
    out: list[tuple[str, str | None]] = []
    for tag in split_tags(raw):
        reason = _drop_reason(tag)
        if reason is None:
            lowered = tag.lower()
            if lowered in seen:
                reason = "duplikat"
            else:
                seen.add(lowered)
        out.append((tag, reason))
    return out


def clean_tags(raw: str | None) -> str:
    """Bersihkan string tag berita dari entri yang tidak informatif."""
    if not raw:
        return ""
    return " | ".join(tag for tag, reason in inspect_tags(raw) if reason is None)
