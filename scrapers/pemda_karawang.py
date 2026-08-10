import re

import pandas as pd
import requests
from bs4 import BeautifulSoup

from utils.tags import clean_tags as _clean_tags

PEMDA_SOURCE = "Pemda Karawang"
PEMDA_BASE   = "https://karawangkab.go.id"
PEMDA_URL    = "https://karawangkab.go.id/berita/"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    "Referer": "https://www.google.com/"
}

# ── Pembersih konten ───────────────────────────────────────────────────────────

_PK_BOILERPLATE_PREFIXES = (
    "BACA JUGA",
    "Sumber:",
    "Simak breaking news",
    "Ikuti kami",
    "Dapatkan informasi",
)

_PK_CITY_PREFIX = re.compile(
    r"^Kab\.?\s*Karawang\s*[,–\-]+\s*",
    re.IGNORECASE,
)


def clean_content(text: str) -> str:
    lines = text.split("\n")
    cleaned: list[str] = []
    for i, raw_line in enumerate(lines):
        line = raw_line.strip()
        if any(line.startswith(prefix) for prefix in _PK_BOILERPLATE_PREFIXES):
            continue
        if i == 0:
            line = _PK_CITY_PREFIX.sub("", line).strip()
        if line:
            cleaned.append(line)
    return "\n".join(cleaned)


# ── Scrape satu artikel ────────────────────────────────────────────────────────

def scrape_article(url: str) -> dict:
    res = requests.get(url, headers=headers, timeout=15)
    soup = BeautifulSoup(res.text, "html.parser")

    title_el = soup.select_one("h1#page-title")
    title = title_el.get_text(strip=True) if title_el else None

    date_el = soup.select_one("div.datetime")
    date = date_el.get_text(strip=True) if date_el else None

    tags = [t.get_text(strip=True) for t in soup.select("div.field-name-field-tags-berita li a")]

    content_el = soup.select_one("div.field-name-body div.field-item")
    paragraphs = []
    if content_el:
        paragraphs = [p.get_text(strip=True) for p in content_el.find_all("p")]

    return {
        "judul":   title,
        "penulis": None,
        "tanggal": date,
        "tags":    _clean_tags(", ".join(tags)),
        "isi":     clean_content("\n".join(paragraphs)),
        "url":     url,
    }


# ── Scrape listing (fungsi mandiri) ───────────────────────────────────────────

def scrape_pemda(n: int) -> list:
    results = []
    page = 0
    article_count = 0

    while article_count < n:
        url = f"{PEMDA_URL}?page={page}" if page > 0 else PEMDA_URL
        print(f"\nMembuka halaman {page + 1}: {url}")

        res = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        items = soup.select("div.views-row")

        if not items:
            break

        for item in items:
            if article_count >= n:
                break
            link = item.select_one("div.views-field-title span.field-content a")
            if link:
                href = link.get("href", "")
                if not href:
                    continue
                article_url = href if href.startswith("http") else PEMDA_BASE + href
                data = scrape_article(article_url)
                article_count += 1
                print(f"Berhasil scrape berita {article_count}: {data['judul']}")
                results.append(data)

        page += 1

    return results


# ── API untuk dipanggil dari Flask ────────────────────────────────────────────

def scrape_new_articles(
    existing_urls: set,
    max_articles: int = 150,
    on_progress=None,
) -> list:
    """
    Scrape berita baru dari Pemda Karawang (karawangkab.go.id).
    Berhenti saat menemukan URL duplikat atau mencapai max_articles.
    on_progress(scraped_count, source_name): callback opsional.
    Kembalikan list dict {title, date, url, content, tags, source}.
    """
    new_articles = []
    page = 0
    stop = False

    def log(msg: str):
        print(f"[PemdaKarawang] {msg}")

    while not stop and len(new_articles) < max_articles:
        url = f"{PEMDA_URL}?page={page}" if page > 0 else PEMDA_URL
        log(f"Halaman listing {page + 1}: {url}")

        try:
            res = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(res.text, "html.parser")
        except Exception as exc:
            log(f"Gagal membuka halaman listing: {exc}")
            break

        items = soup.select("div.views-row")
        if not items:
            log("Tidak ada artikel ditemukan, berhenti.")
            break

        for item in items:
            if len(new_articles) >= max_articles or stop:
                break

            link = item.select_one("div.views-field-title span.field-content a")
            if not link:
                continue

            href = link.get("href", "")
            if not href:
                continue

            article_url = href if href.startswith("http") else PEMDA_BASE + href

            if article_url in existing_urls:
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
                    "source":  PEMDA_SOURCE,
                }
                new_articles.append(article)
                existing_urls.add(article_url)
                if on_progress:
                    on_progress(len(new_articles), PEMDA_SOURCE)
            except Exception as exc:
                log(f"Error scrape artikel {article_url}: {exc}")

        if stop or len(new_articles) >= max_articles:
            break

        page += 1

    log(f"Selesai. {len(new_articles)} berita baru ditemukan.")
    return new_articles


# ── Entry point (jalan mandiri) ────────────────────────────────────────────────

if __name__ == "__main__":
    data = scrape_pemda(100)
    df = pd.DataFrame(data)
    df.to_excel("pemda_karawang.xlsx", index=False)
    print("\nData berhasil disimpan ke pemda_karawang.xlsx")
