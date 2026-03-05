import requests
from bs4 import BeautifulSoup
import pandas as pd

PANTURAPOST_SOURCE = "Pantura Post"
PANTURAPOST_BASE   = "https://www.panturapost.com"
PANTURAPOST_TEGAL  = "https://www.panturapost.com/tegal"

headers = {"User-Agent": "Mozilla/5.0"}


# ── Scrape satu artikel ────────────────────────────────────────────────────────

def scrape_article(url):
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, "html.parser")

    title = soup.select_one(".read__title")
    title = title.get_text(strip=True) if title else None

    author = soup.select_one(".read__info__author a")
    author = author.get_text(strip=True) if author else None

    date = soup.select_one(".read__info__date")
    date = date.get_text(strip=True) if date else None

    tags = [t.get_text(strip=True) for t in soup.select(".tag__list a")]

    page_links = [url]
    paging = soup.select(".paging__item a.paging__link")

    for link in paging:
        text = link.get_text(strip=True)
        if text.lower() != "selanjutnya":
            href = link.get("href")
            if href and href not in page_links:
                page_links.append(href)

    all_content = []
    for page in page_links:
        res = requests.get(page, headers=headers)
        soup = BeautifulSoup(res.text, "html.parser")
        content = soup.select_one(".read__content.clearfix")
        if content:
            paragraphs = [p.get_text(strip=True) for p in content.find_all("p")]
            all_content.extend(paragraphs)

    return {
        "judul": title,
        "penulis": author,
        "tanggal": date,
        "tags": ", ".join(tags),
        "isi": "\n".join(all_content),
        "url": url
    }


# ── Scrape listing (fungsi asli, tetap tersedia) ───────────────────────────────

def scrape_tegal(n):
    url = PANTURAPOST_TEGAL
    results = []
    page_number = 1
    article_count = 0

    while article_count < n:
        print(f"\nMembuka halaman {page_number}")
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, "html.parser")
        items = soup.select(".latest__item")

        for item in items:
            if article_count >= n:
                break
            link = item.select_one("a.latest__link")
            if link:
                article_url = link["href"]
                data = scrape_article(article_url)
                article_count += 1
                print(f"Berhasil scrape berita {article_count}")
                results.append(data)

        next_page = soup.select_one(".paging__link.paging__link--next")
        if next_page and article_count < n:
            href = next_page.get("href", "")
            url = href if href.startswith("http") else PANTURAPOST_TEGAL + href
            page_number += 1
        else:
            break

    return results


# ── API untuk dipanggil dari Flask ────────────────────────────────────────────

def scrape_new_articles(
    existing_urls: set,
    max_articles: int = 150,
    on_progress=None,
) -> list:
    """
    Scrape berita baru dari Pantura Post (panturapost.com/tegal).
    Berhenti saat menemukan URL duplikat atau mencapai max_articles.
    on_progress(scraped_count, source_name): callback opsional.
    Kembalikan list dict {title, date, url, content, tags, source}.
    """
    new_articles = []
    url = PANTURAPOST_TEGAL
    page_number = 1
    stop = False

    def log(msg: str):
        print(f"[PanturaPost] {msg}")

    while not stop and len(new_articles) < max_articles:
        log(f"Halaman listing {page_number}: {url}")

        try:
            res = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(res.text, "html.parser")
        except Exception as exc:
            log(f"Gagal membuka halaman listing: {exc}")
            break

        items = soup.select(".latest__item")
        if not items:
            log("Tidak ada artikel ditemukan, berhenti.")
            break

        for item in items:
            if len(new_articles) >= max_articles or stop:
                break

            link = item.select_one("a.latest__link")
            if not link:
                continue

            article_url = link.get("href", "")
            if not article_url:
                continue

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
                    "source":  PANTURAPOST_SOURCE,
                }
                new_articles.append(article)
                existing_urls.add(article_url)
                if on_progress:
                    on_progress(len(new_articles), PANTURAPOST_SOURCE)
            except Exception as exc:
                log(f"Error scrape artikel {article_url}: {exc}")

        if stop or len(new_articles) >= max_articles:
            break

        next_page = soup.select_one(".paging__link.paging__link--next")
        if next_page:
            href = next_page.get("href", "")
            url = href if href.startswith("http") else PANTURAPOST_TEGAL + href
            page_number += 1
        else:
            log("Tidak ada halaman berikutnya.")
            break

    log(f"Selesai. {len(new_articles)} berita baru ditemukan.")
    return new_articles


# ── Entry point (jalan mandiri) ────────────────────────────────────────────────

if __name__ == "__main__":
    data = scrape_tegal(100)
    df = pd.DataFrame(data)
    df.to_excel("panturapost_tegal.xlsx", index=False)
    print("\nData berhasil disimpan ke panturapost_tegal.xlsx")