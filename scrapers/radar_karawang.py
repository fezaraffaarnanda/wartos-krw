import re

import pandas as pd
import requests
from bs4 import BeautifulSoup

from utils.tags import clean_tags as _clean_tags

RADARKARAWANG_SOURCE = "Radar Karawang"
RADARKARAWANG_BASE   = "https://radarkarawang.id"
RADARKARAWANG_URL    = "https://radarkarawang.id/category/karawang/"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    "Referer": "https://www.google.com/"
}

# ── Pembersih konten ───────────────────────────────────────────────────────────

_RK_DOMAIN_REGEX = re.compile(r"radarkarawang\.id", re.IGNORECASE)

_RK_ZERO_WIDTH_REGEX = re.compile(r"[​‎‏‌­]")

_RK_BOILERPLATE_PREFIXES = (
    "BACA JUGA",
    "Sumber:",
    "Simak breaking news",
    "Ikuti kami",
    "Dapatkan informasi",
)


def clean_content(text: str) -> str:
    text = _RK_ZERO_WIDTH_REGEX.sub("", text)
    text = _RK_DOMAIN_REGEX.sub("", text)

    cleaned: list[str] = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if any(line.startswith(prefix) for prefix in _RK_BOILERPLATE_PREFIXES):
            continue
        if line:
            cleaned.append(line)
    return "\n".join(cleaned)


# ── Scrape satu artikel ────────────────────────────────────────────────────────

def scrape_article(url: str) -> dict:
    res = requests.get(url, headers=headers, timeout=15)
    soup = BeautifulSoup(res.text, "html.parser")

    title_el = soup.select_one("h1.post-title.entry-title")
    title = title_el.get_text(strip=True) if title_el else None

    author_el = soup.select_one(".meta-author a.author-name")
    author = None
    if author_el:
        author = author_el.get("title") or author_el.get_text(strip=True)

    date_el = soup.select_one("span.date.meta-item")
    date = date_el.get_text(strip=True) if date_el else None

    tags = [t.get_text(strip=True) for t in soup.select(".post-bottom-tags .tagcloud a")]

    content_el = soup.select_one("div.entry-content.entry.clearfix")
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

def scrape_karawang(n: int) -> list:
    url = RADARKARAWANG_URL
    results = []
    page_number = 1
    article_count = 0

    while article_count < n:
        print(f"\nMembuka halaman {page_number}")
        res = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        items = soup.select("li.post-item")

        for item in items:
            if article_count >= n:
                break
            link = item.select_one("h2.post-title a")
            if link:
                article_url = link.get("href", "")
                if not article_url:
                    continue
                data = scrape_article(article_url)
                article_count += 1
                print(f"Berhasil scrape berita {article_count}: {data['judul']}")
                results.append(data)

        next_page = next(
            (a for a in soup.find_all("a") if "Next page" in a.get_text()),
            None,
        )
        if next_page and article_count < n:
            url = next_page.get("href", "")
            page_number += 1
        else:
            break

    return results


# ── API untuk dipanggil dari Flask ────────────────────────────────────────────

def scrape_new_articles(
    existing_urls: set,
    max_articles: int = 150,
    on_progress=None,
    backfill: bool = False,
) -> list:
    """
    Scrape berita baru dari Radar Karawang.
    Berhenti saat menemukan URL duplikat atau mencapai max_articles.
    backfill=True: duplikat di-skip (bukan berhenti) supaya bisa jalan terus
    ke berita lama di halaman berikutnya -- dipakai untuk isi database dari
    beberapa bulan ke belakang.
    on_progress(scraped_count, source_name): callback opsional.
    Kembalikan list dict {title, date, url, content, tags, source}.
    """
    new_articles = []
    url = RADARKARAWANG_URL
    page_number = 1
    stop = False

    def log(msg: str):
        print(f"[RadarKarawang] {msg}")

    while not stop and len(new_articles) < max_articles:
        log(f"Halaman listing {page_number}: {url}")

        try:
            res = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(res.text, "html.parser")
        except Exception as exc:
            log(f"Gagal membuka halaman listing: {exc}")
            break

        items = soup.select("li.post-item")
        if not items:
            log("Tidak ada artikel ditemukan, berhenti.")
            break

        for item in items:
            if len(new_articles) >= max_articles or stop:
                break

            link = item.select_one("h2.post-title a")
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
                    "source":  RADARKARAWANG_SOURCE,
                }
                new_articles.append(article)
                existing_urls.add(article_url)
                if on_progress:
                    on_progress(len(new_articles), RADARKARAWANG_SOURCE)
            except Exception as exc:
                log(f"Error scrape artikel {article_url}: {exc}")

        if stop or len(new_articles) >= max_articles:
            break

        next_page = next(
            (a for a in soup.find_all("a") if "Next page" in a.get_text()),
            None,
        )
        if next_page:
            url = next_page.get("href", "")
            page_number += 1
        else:
            log("Tidak ada halaman berikutnya.")
            break

    log(f"Selesai. {len(new_articles)} berita baru ditemukan.")
    return new_articles


# ── Entry point (jalan mandiri) ────────────────────────────────────────────────

if __name__ == "__main__":
    data = scrape_karawang(100)
    df = pd.DataFrame(data)
    df.to_excel("radar_karawang.xlsx", index=False)
    print("\nData berhasil disimpan ke radar_karawang.xlsx")
