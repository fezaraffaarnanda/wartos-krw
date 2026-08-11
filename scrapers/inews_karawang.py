import re

import pandas as pd
import requests
from bs4 import BeautifulSoup

from utils.tags import clean_tags as _clean_tags

INEWS_SOURCE   = "iNews Karawang"
INEWS_BASE     = "https://karawang.inews.id"
INEWS_URL      = "https://karawang.inews.id/indeks/karawang/all"
INEWS_PAGE_STEP = 12

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    "Referer": "https://www.google.com/"
}

# ── Pembersih konten ───────────────────────────────────────────────────────────

_IN_CITY_PREFIX = re.compile(
    r"^KARAWANG\s*,\s*iNEWSKarawang\.id\s*[–\-]+\s*",
    re.IGNORECASE,
)

_IN_EDITOR_LINE = re.compile(r"^Editor\s*:\s*", re.IGNORECASE)

_IN_BOILERPLATE_PREFIXES = (
    "BACA JUGA",
    "Baca Juga",
    "Sumber:",
    "Simak breaking news",
    "Ikuti kami",
    "Dapatkan informasi",
    "Follow Whatsapp",
)


def clean_content(text: str) -> str:
    lines = text.split("\n")
    cleaned: list[str] = []
    for i, raw_line in enumerate(lines):
        line = raw_line.strip()
        if any(line.startswith(prefix) for prefix in _IN_BOILERPLATE_PREFIXES):
            continue
        if _IN_EDITOR_LINE.match(line):
            continue
        if i == 0:
            line = _IN_CITY_PREFIX.sub("", line).strip()
        if line:
            cleaned.append(line)
    return "\n".join(cleaned)


# ── Scrape satu artikel ────────────────────────────────────────────────────────

def scrape_article(url: str) -> dict:
    res = requests.get(url, headers=headers, timeout=15)
    soup = BeautifulSoup(res.text, "html.parser")

    title_el = soup.select_one("h1.headerTitle")
    title = title_el.get_text(strip=True) if title_el else None

    date_el = soup.select_one("div.createdAt")
    date = date_el.get_text(strip=True) if date_el else None

    author_el = soup.select_one("ul.author li.authorList a")
    author = author_el.get_text(strip=True) if author_el else None

    tags = [t.get_text(strip=True) for t in soup.select("div.tags li.tagList a")]

    content_el = soup.select_one("div.bodyArticle")
    paragraphs = []
    if content_el:
        paragraphs = [p.get_text(strip=True) for p in content_el.find_all("p")]

    return {
        "judul":   title,
        "penulis": author,
        "tanggal": date,
        "tags":    _clean_tags(", ".join(tags)),
        "isi":     clean_content("\n".join(paragraphs)),
        "url":     url,
    }


# ── Scrape listing (fungsi mandiri) ───────────────────────────────────────────

def scrape_inews(n: int) -> list:
    results = []
    offset = 0
    article_count = 0

    while article_count < n:
        url = INEWS_URL if offset == 0 else f"{INEWS_URL}/{offset}"
        print(f"\nMembuka halaman offset {offset}: {url}")

        res = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        items = soup.select("div.box-list-news")

        if not items:
            break

        for item in items:
            if article_count >= n:
                break
            link = item.select_one("div.list-desk a[href*='/read/']")
            if link:
                article_url = link.get("href", "")
                if not article_url:
                    continue
                data = scrape_article(article_url)
                article_count += 1
                print(f"Berhasil scrape berita {article_count}: {data['judul']}")
                results.append(data)

        offset += INEWS_PAGE_STEP

    return results


# ── API untuk dipanggil dari Flask ────────────────────────────────────────────

def scrape_new_articles(
    existing_urls: set,
    max_articles: int = 150,
    on_progress=None,
    backfill: bool = False,
) -> list:
    """
    Scrape berita baru dari iNews Karawang.
    Berhenti saat menemukan URL duplikat atau mencapai max_articles.
    backfill=True: duplikat di-skip (bukan berhenti) supaya bisa jalan terus
    ke berita lama di halaman berikutnya -- dipakai untuk isi database dari
    beberapa bulan ke belakang.
    on_progress(scraped_count, source_name): callback opsional.
    Kembalikan list dict {title, date, url, content, tags, source}.
    """
    new_articles = []
    offset = 0
    stop = False

    def log(msg: str):
        print(f"[iNewsKarawang] {msg}")

    while not stop and len(new_articles) < max_articles:
        url = INEWS_URL if offset == 0 else f"{INEWS_URL}/{offset}"
        log(f"Halaman listing offset {offset}: {url}")

        try:
            res = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(res.text, "html.parser")
        except Exception as exc:
            log(f"Gagal membuka halaman listing: {exc}")
            break

        items = soup.select("div.box-list-news")
        if not items:
            log("Tidak ada artikel ditemukan, berhenti.")
            break

        for item in items:
            if len(new_articles) >= max_articles or stop:
                break

            link = item.select_one("div.list-desk a[href*='/read/']")
            if not link:
                continue

            article_url = link.get("href", "")
            if not article_url:
                continue

            if article_url in existing_urls:
                if backfill:
                    log(f"Duplikat dilewati (mode backfill): {article_url}")
                    continue
                log(f"Duplikat ditemukan, berhenti: {article_url}")
                stop = True
                break

            log(f"Scraping [{len(new_articles)+1}]: {article_url}")
            try:
                data = scrape_article(article_url)
                article = {
                    "title":   data["judul"] or "",
                    "date":    data["tanggal"] or "",
                    "url":     article_url,
                    "content": data["isi"] or "",
                    "tags":    data["tags"] or "",
                    "source":  INEWS_SOURCE,
                }
                new_articles.append(article)
                existing_urls.add(article_url)
                if on_progress:
                    on_progress(len(new_articles), INEWS_SOURCE)
            except Exception as exc:
                log(f"Error scrape artikel {article_url}: {exc}")

        if stop or len(new_articles) >= max_articles:
            break

        offset += INEWS_PAGE_STEP

    log(f"Selesai. {len(new_articles)} berita baru ditemukan.")
    return new_articles


# ── Entry point (jalan mandiri) ────────────────────────────────────────────────

if __name__ == "__main__":
    data = scrape_inews(100)
    df = pd.DataFrame(data)
    df.to_excel("inews_karawang.xlsx", index=False)
    print("\nData berhasil disimpan ke inews_karawang.xlsx")
