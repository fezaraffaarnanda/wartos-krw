import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import pandas as pd
import time
import random

TRIBUN_SOURCE    = "Tribun Jateng"
TRIBUN_START_URL = "https://jateng.tribunnews.com/topic/berita-kabupaten-tegal"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    "Referer": "https://www.google.com/"
}
session = requests.Session()
session.headers.update(headers)


# ── Helper ─────────────────────────────────────────────────────────────────────

def get_page(url):
    try:
        res = session.get(url, timeout=5)
        if res.status_code == 200:
            return res.text
    except Exception:
        pass
    return None


# ── Scrape satu artikel ────────────────────────────────────────────────────────

def scrape_tribun(url):
    original_url = url
    judul = None
    penulis = None
    waktu = None
    tags = []
    isi_all = []

    while url:
        html = get_page(url)
        if not html:
            break

        soup = BeautifulSoup(html, "html.parser")

        if judul is None:
            tag = soup.select_one("h1")
            if tag:
                judul = tag.get_text(strip=True)

        if penulis is None:
            tag = soup.select_one("h5#penulis a")
            if tag:
                penulis = tag.get_text(strip=True)

        if waktu is None:
            tag = soup.select_one("time span")
            if tag:
                waktu = tag.get_text(strip=True)

        if not tags:
            for tag in soup.select(".tagcloud3"):
                tags.append(tag.get_text(strip=True))

        for p in soup.select(".txt-article p:not(.baca)"):
            isi_all.append(p.get_text(strip=True))

        next_page = None
        active = soup.select_one(".page-number a.active")
        if active:
            next_tag = active.find_next("a")
            if next_tag:
                next_page = urljoin(url, next_tag["href"])

        url = next_page
        time.sleep(random.uniform(2, 4))

    return {
        "judul": judul,
        "penulis": penulis,
        "waktu": waktu,
        "isi": " ".join(isi_all),
        "tags": ", ".join(tags),
        "url": original_url
    }


# ── Scrape index (fungsi asli, tetap tersedia) ─────────────────────────────────

def scrape_index(start_url, target_n):
    results = []
    page_url = start_url

    while len(results) < target_n:
        print("Membuka halaman:", page_url)
        html = get_page(page_url)
        if not html:
            break

        soup = BeautifulSoup(html, "html.parser")
        ul = soup.select_one(".lsi.bdr ul")
        if not ul:
            print("ul tidak ditemukan")
            break

        items = ul.find_all("li")
        for li in items:
            link_tag = li.select_one("h3 a")
            if not link_tag:
                continue
            link = link_tag["href"]
            judul = link_tag.get_text(strip=True)
            print("Scrape:", judul)
            artikel = scrape_tribun(link)
            results.append(artikel)
            print("Total:", len(results))
            if len(results) >= target_n:
                break
            time.sleep(random.uniform(3, 6))

        next_tag = soup.select_one("a[rel='next']")
        if next_tag:
            page_url = next_tag["href"]
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
    Scrape berita baru dari Tribun Jateng (topic berita Kabupaten Tegal).
    Berhenti saat menemukan URL duplikat atau mencapai max_articles.
    on_progress(scraped_count, source_name): callback opsional.
    Kembalikan list dict {title, date, url, content, tags, source}.
    """
    new_articles = []
    page_url = TRIBUN_START_URL
    stop = False

    def log(msg: str):
        print(f"[TribunJateng] {msg}")

    while not stop and len(new_articles) < max_articles:
        log(f"Membuka halaman listing: {page_url}")

        html = get_page(page_url)
        if not html:
            log("Gagal membuka halaman listing, berhenti.")
            break

        soup = BeautifulSoup(html, "html.parser")
        ul = soup.select_one(".lsi.bdr ul")
        if not ul:
            log("Tidak ada daftar artikel, berhenti.")
            break

        items = ul.find_all("li")
        for li in items:
            if len(new_articles) >= max_articles or stop:
                break

            link_tag = li.select_one("h3 a")
            if not link_tag:
                continue

            article_url = link_tag.get("href", "")
            if not article_url:
                continue

            if article_url in existing_urls:
                log(f"Duplikat ditemukan, berhenti: {article_url}")
                stop = True
                break

            log(f"Scraping [{len(new_articles)+1}]: {article_url}")
            try:
                data = scrape_tribun(article_url)
                tags_raw = data.get("tags", "")
                tags_str = " | ".join(
                    t.strip() for t in tags_raw.replace(",", "|").split("|") if t.strip()
                ) if tags_raw else ""

                article = {
                    "title":   data.get("judul") or "",
                    "date":    data.get("waktu") or "",
                    "url":     article_url,
                    "content": data.get("isi") or "",
                    "tags":    tags_str,
                    "source":  TRIBUN_SOURCE,
                }
                new_articles.append(article)
                existing_urls.add(article_url)
                if on_progress:
                    on_progress(len(new_articles), TRIBUN_SOURCE)
            except Exception as exc:
                log(f"Error scrape artikel {article_url}: {exc}")

            time.sleep(random.uniform(1.5, 3))

        if stop or len(new_articles) >= max_articles:
            break

        next_tag = soup.select_one("a[rel='next']")
        if next_tag:
            page_url = next_tag["href"]
        else:
            log("Tidak ada halaman berikutnya.")
            break

    log(f"Selesai. {len(new_articles)} berita baru ditemukan.")
    return new_articles


# ── Entry point (jalan mandiri) ────────────────────────────────────────────────

if __name__ == "__main__":
    data = scrape_index(TRIBUN_START_URL, 100)
    df = pd.DataFrame(data)
    df.to_excel("tribun_tegal_berkah.xlsx", index=False)
    print("\nScraping selesai")
    print("File tersimpan: tribun_tegal_berkah.xlsx")