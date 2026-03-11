"""
scraping_tegal.py — Scraper Berita Setda Kabupaten Tegal
Sumber: https://setda.tegalkab.go.id/author/adminhumas/

Mengikuti contract scraper standar proyek:
    scrape_new_articles(existing_urls, max_articles, on_progress) -> list[dict]
    Setiap dict: {title, date, url, content, tags, source}

Cara pakai standalone:
    python -m scrapers.scraping_tegal
"""

import random
import re
import sys, os
import time

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.utils import clean_tags as _clean_tags

# ── Konstanta ──────────────────────────────────────────────────────────────────

BASE_URL   = "https://setda.tegalkab.go.id"
AUTHOR_URL = f"{BASE_URL}/author/adminhumas/"
SOURCE     = "Setda Tegal"

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
    "Connection":      "keep-alive",
    "Referer":         "https://www.google.com/",
}

# Mapping nama bulan Inggris → Indonesia (format yang dipakai situs JNews)
_BULAN_EN_ID = {
    "January":   "Januari",
    "February":  "Februari",
    "March":     "Maret",
    "April":     "April",
    "May":       "Mei",
    "June":      "Juni",
    "July":      "Juli",
    "August":    "Agustus",
    "September": "September",
    "October":   "Oktober",
    "November":  "November",
    "December":  "Desember",
}

# Mapping nomor bulan → nama Indonesia (untuk format ISO datetime attribute)
_BULAN_NUM_ID = {
    "01": "Januari",  "02": "Februari", "03": "Maret",
    "04": "April",    "05": "Mei",      "06": "Juni",
    "07": "Juli",     "08": "Agustus",  "09": "September",
    "10": "Oktober",  "11": "November", "12": "Desember",
}

# Regex: "March 9, 2026" atau "March 09, 2026" (teks tampilan)
_DATE_REGEX = re.compile(
    r"^(\w+)\s+(\d{1,2}),?\s+(\d{4})$",
)

# Regex: ISO format datetime attribute JNews ("2025-10-28T01:00:00+00:00")
_ISO_DATE_REGEX = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})",
)

# ── Normalisasi tanggal ────────────────────────────────────────────────────────

def _normalize_date(raw: str) -> str:
    """
    Konversi tanggal situs ke format standar proyek:
    "DD MMMM YYYY, HH:MM WIB" — contoh: "9 Maret 2026, 08:00 WIB"

    Format yang didukung:
      - ISO datetime attribute JNews : "2025-10-28T01:00:00+00:00"
      - Teks tampilan halaman        : "March 9, 2026"

    Jika tidak dikenali, kembalikan apa adanya.
    """
    raw = raw.strip()
    if not raw:
        return raw

    # ── Format ISO (datetime attribute) ───────────────────────────────────────
    m_iso = _ISO_DATE_REGEX.search(raw)
    if m_iso:
        tahun, bulan_num, hari, jam, menit = (
            m_iso.group(1), m_iso.group(2), m_iso.group(3),
            m_iso.group(4), m_iso.group(5),
        )
        bulan_id = _BULAN_NUM_ID.get(bulan_num, bulan_num)
        return f"{int(hari)} {bulan_id} {tahun}, {jam}:{menit} WIB"

    # ── Format teks tampilan: "March 9, 2026" ─────────────────────────────────
    m = _DATE_REGEX.match(raw)
    if m:
        bulan_en, hari, tahun = m.group(1), m.group(2), m.group(3)
        bulan_id = _BULAN_EN_ID.get(bulan_en, bulan_en)
        return f"{int(hari)} {bulan_id} {tahun}, 08:00 WIB"

    return raw


# ── Pembersih konten ───────────────────────────────────────────────────────────

_BOILERPLATE_PREFIXES = (
    "BACA JUGA",
    "Baca juga",
    "Sumber:",
    "Editor:",
    "Reporter:",
    "Penulis:",
)

_BOILERPLATE_REGEX = re.compile(
    r"Ikuti kami di Google News"
    r"|Cek Berita dan Artikel lainnya"
    r"|Dapatkan informasi terkini",
    re.IGNORECASE,
)


def _clean_content(text: str) -> str:
    """Bersihkan konten dari boilerplate situs JNews."""
    lines = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if any(line.startswith(p) for p in _BOILERPLATE_PREFIXES):
            continue
        if _BOILERPLATE_REGEX.search(line):
            continue
        lines.append(line)
    return "\n".join(lines)


# ── Scraping halaman listing ───────────────────────────────────────────────────

def _get_article_links_from_page(soup: BeautifulSoup) -> list[str]:
    """Ambil semua URL artikel dari satu halaman listing."""
    links = []
    for art in soup.select("article.jeg_post"):
        a = art.select_one("h3.jeg_post_title a, h2.jeg_post_title a")
        if a and a.get("href"):
            links.append(a["href"])
    return links


def _get_next_page_url(soup: BeautifulSoup) -> str | None:
    """Cari URL halaman berikutnya dari navigasi paginasi."""
    btn = soup.select_one("a.page_nav.next, a.next.page-numbers")
    return btn["href"] if btn and btn.get("href") else None


# ── Scraping halaman artikel ───────────────────────────────────────────────────

def _scrape_article(url: str) -> dict | None:
    """
    Scrape satu halaman artikel. Return dict atau None jika gagal.
    Internal key sudah menggunakan bahasa Inggris sesuai contract.
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as exc:
        print(f"[Setda Tegal] Gagal mengambil {url}: {exc}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    # Judul
    title_el = soup.select_one(".jeg_post_title")
    title    = title_el.get_text(strip=True) if title_el else ""
    if not title:
        return None

    # Tanggal — dari meta date atau teks .jeg_meta_date
    date_raw = ""
    date_el  = soup.select_one(".jeg_meta_date a, .jeg_meta_date time")
    if date_el:
        date_raw = date_el.get("datetime", "") or date_el.get_text(strip=True)

    # Isi artikel
    content_div = soup.select_one(".content-inner, .jeg_post_content")
    content     = ""
    if content_div:
        # Hapus widget inline "baca juga"
        for div in content_div.select(
            "div.jnews_inline_related_post_wrapper, "
            "div.jnews_block_8, "
            ".ads-code"
        ):
            div.decompose()
        paragraphs = [p.get_text(strip=True) for p in content_div.select("p") if p.get_text(strip=True)]
        content    = _clean_content("\n".join(paragraphs))

    # Tag
    tags_els = soup.select(".jeg_post_tags a")
    tags     = _clean_tags(", ".join(t.get_text(strip=True) for t in tags_els))

    return {
        "title":   title,
        "date":    _normalize_date(date_raw),
        "url":     url,
        "content": content,
        "tags":    tags,
        "source":  SOURCE,
    }


# ── Contract utama ─────────────────────────────────────────────────────────────

def scrape_new_articles(
    existing_urls: set,
    max_articles:  int = 50,
    on_progress=None,
) -> list[dict]:
    """
    Scrape berita baru dari Setda Kabupaten Tegal.

    Args:
        existing_urls: set URL yang sudah ada di DB — berhenti saat duplikat ditemukan.
        max_articles:  batas maksimum artikel baru yang dikembalikan.
        on_progress(count, msg): callback progress opsional.

    Returns:
        list dict {title, date, url, content, tags, source}
    """
    new_articles: list[dict] = []

    def log(msg: str):
        print(f"[Setda Tegal] {msg}")
        if on_progress:
            on_progress(len(new_articles), msg)

    page_url = AUTHOR_URL
    page_num = 1
    stop     = False

    while page_url and not stop and len(new_articles) < max_articles:
        log(f"Membuka halaman listing {page_num}: {page_url}")

        try:
            r    = requests.get(page_url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
        except Exception as exc:
            log(f"[ERROR] Gagal membuka halaman listing: {exc}")
            break

        links = _get_article_links_from_page(soup)
        log(f"Ditemukan {len(links)} artikel di halaman {page_num}.")

        if not links:
            break

        for link in links:
            if len(new_articles) >= max_articles:
                stop = True
                break

            if link in existing_urls:
                log(f"Duplikat ditemukan, berhenti: {link}")
                stop = True
                break

            log(f"Scraping: {link}")
            article = _scrape_article(link)
            if article:
                new_articles.append(article)
                existing_urls.add(link)
                log(f"  OK — {article['title'][:60]}")
            else:
                log(f"  [LEWATI] Gagal scraping: {link}")

            time.sleep(random.uniform(1.0, 2.0))

        if stop:
            break

        page_url = _get_next_page_url(soup)
        page_num += 1
        time.sleep(random.uniform(1.0, 1.5))

    log(f"Selesai. Total berita baru: {len(new_articles)}")
    return new_articles


# ── Standalone test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Scraper Setda Kabupaten Tegal — uji standalone")
    print("=" * 60)
    hasil = scrape_new_articles(existing_urls=set(), max_articles=3)
    for i, a in enumerate(hasil, 1):
        print(f"\n[{i}] {a['title']}")
        print(f"    Tanggal : {a['date']}")
        print(f"    URL     : {a['url']}")
        print(f"    Tags    : {a['tags']}")
        print(f"    Konten  : {a['content'][:120]}...")
    print(f"\nTotal: {len(hasil)} artikel")