import re
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random

BASE_URL    = "https://www.kompas.com/tag/tegal"
KOMPAS_SOURCE = "Kompas"
N = 100

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    "Referer": "https://www.google.com/"
}

session = requests.Session()
session.headers.update(HEADERS)


# ── Pembersih konten ───────────────────────────────────────────────────────────

_KP_DOMAIN_REGEX = re.compile(r"kompas\.com", re.IGNORECASE)

_KP_BOILERPLATE_PREFIXES = (
    "BACA JUGA",
    "Sumber:",
    "Simak breaking news",
    "Ikuti kami di Google News",
    "Dapatkan informasi terkini",
    "Editor:",
    "Penulis:",
)

_KP_BOILERPLATE_REGEX = re.compile(
    r"Cek Berita dan Artikel lainnya\s*di\s*Google\s*News"
    r"|Ikuti kami di Google News"
    r"|Simak breaking news"
    r"|Dapatkan informasi terkini",
    re.IGNORECASE,
)


def clean_content(text: str) -> str:
    """
    Bersihkan konten artikel Kompas dari watermark dan noise:
      - Domain kompas.com
      - Baris BACA JUGA, Sumber:, Editor:, Penulis:, footer Google News
      - Baris kosong dan separator
    """
    text = _KP_DOMAIN_REGEX.sub("", text)
    text = re.sub(r"\(\*+\)", "", text)

    cleaned: list[str] = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if any(line.startswith(prefix) for prefix in _KP_BOILERPLATE_PREFIXES):
            continue
        if _KP_BOILERPLATE_REGEX.search(line):
            continue
        if line == "--":
            continue
        line = re.sub(r"\s*--$", "", line).strip()
        if line:
            cleaned.append(line)
    return "\n".join(cleaned)


# =============================
# AMBIL HTML
# =============================
def get_soup(url):

    try:
        res = session.get(url, timeout=10)
        res.raise_for_status()
        return BeautifulSoup(res.text, "html.parser")

    except Exception:
        print("Error membuka:", url)
        return None


# =============================
# SCRAPE ARTIKEL
# =============================
def scrape_article(url):

    soup = get_soup(url)

    if not soup:
        return None

    title_tag = soup.select_one(".read__title")
    date_tag = soup.select_one(".read__time")

    title = title_tag.text.strip() if title_tag else ""
    date = date_tag.text.strip() if date_tag else ""

    # Filter berita tidak relevan
    if "Jadwal Imsak" in title or "Jadwal Buka Puasa" in title:
        return None

    # =============================
    # PENULIS
    # =============================
    authors = []

    credits = soup.select(".credit-title-name")

    for c in credits:
        txt = c.text.strip()
        if "Editor" not in txt:
            authors.append(txt)

    author = ", ".join(authors)

    content = []

    # =============================
    # CEK SHOW ALL
    # =============================
    show_all = soup.select_one(".paging__link.paging__link--show")

    if show_all and show_all.get("href", "").startswith("http"):

        show_url = show_all["href"]
        soup = get_soup(show_url)

        if soup:
            paragraphs = soup.select(".read__content p")

            for p in paragraphs:
                content.append(p.text.strip())

    else:

        page_urls = [url]

        pages = soup.select(".paging__wrap .paging__item a")

        for a in pages:

            href = a.get("href")

            if href and href.startswith("http") and href not in page_urls:
                page_urls.append(href)

        # SCRAPE TIAP HALAMAN
        for purl in page_urls:

            psoup = get_soup(purl)

            if not psoup:
                continue

            paragraphs = psoup.select(".read__content p")

            for p in paragraphs:
                content.append(p.text.strip())

    # =============================
    # TAG
    # =============================
    tags = []

    taglist = soup.select(".tagsCloud-tag a")

    for t in taglist:
        tags.append(t.text.strip())

    content = clean_content("\n".join(content))

    return {
        "Judul": title,
        "Tanggal": date,
        "Penulis": author,
        "Isi": content,
        "Url": url,
        "Tags": ", ".join(tags)
    }


# =============================
# SCRAPE HALAMAN TAG
# =============================
def scrape_tag(start_url, target_n):

    data = []
    page_url = start_url
    counter = 1

    while len(data) < target_n:

        print("\n📄 membuka halaman:", page_url)

        soup = get_soup(page_url)

        if not soup:
            break

        articles = soup.select(".articleList .articleItem")

        if not articles:
            print("artikel tidak ditemukan")
            break

        for art in articles:

            if len(data) >= target_n:
                break

            a = art.select_one(".article-link")

            if not a:
                continue

            link = a.get("href")

            # hanya ambil link artikel valid
            if not link or not link.startswith("http"):
                continue

            result = scrape_article(link)

            if result:

                print(f"[{counter}] {result['Judul']}")

                data.append(result)

                counter += 1

            time.sleep(random.uniform(2,4))

        # =============================
        # PAGINATION NEXT
        # =============================
        next_tag = soup.select_one(".paging__link.paging__link--next")

        if next_tag:

            next_link = next_tag.get("href")

            if next_link and next_link.startswith("http"):
                page_url = next_link
            else:
                break

        else:
            print("Halaman terakhir")
            break

    return data


# ── API untuk dipanggil dari Flask ────────────────────────────────────────────

def scrape_new_articles(
    existing_urls: set,
    max_articles: int = 150,
    on_progress=None,
) -> list:
    """
    Scrape berita baru dari Kompas (tag/tegal).
    Berhenti saat menemukan URL duplikat atau mencapai max_articles.
    on_progress(scraped_count, source_name): callback opsional.
    Kembalikan list dict {title, date, url, content, tags, source}.
    """
    new_articles = []
    page_url = BASE_URL
    stop = False

    def log(msg: str):
        print(f"[Kompas] {msg}")

    while not stop and len(new_articles) < max_articles:
        log(f"Membuka halaman listing: {page_url}")

        soup = get_soup(page_url)
        if not soup:
            log("Gagal membuka halaman listing, berhenti.")
            break

        articles = soup.select(".articleList .articleItem")
        if not articles:
            log("Tidak ada artikel ditemukan, berhenti.")
            break

        for art in articles:
            if len(new_articles) >= max_articles or stop:
                break

            a = art.select_one(".article-link")
            if not a:
                continue

            article_url = a.get("href", "")
            if not article_url or not article_url.startswith("http"):
                continue

            if article_url in existing_urls:
                log(f"Duplikat ditemukan, berhenti: {article_url}")
                stop = True
                break

            log(f"Scraping [{len(new_articles)+1}]: {article_url}")
            try:
                data = scrape_article(article_url)
                if not data:
                    log(f"  Artikel dilewati (filter judul): {article_url}")
                    continue

                article = {
                    "title":   data.get("Judul") or "",
                    "date":    data.get("Tanggal") or "",
                    "url":     article_url,
                    "content": data.get("Isi") or "",
                    "tags":    data.get("Tags") or "",
                    "source":  KOMPAS_SOURCE,
                }
                new_articles.append(article)
                existing_urls.add(article_url)
                if on_progress:
                    on_progress(len(new_articles), KOMPAS_SOURCE)
            except Exception as exc:
                log(f"Error scrape artikel {article_url}: {exc}")

            time.sleep(random.uniform(1.5, 3))

        if stop or len(new_articles) >= max_articles:
            break

        next_tag = soup.select_one(".paging__link.paging__link--next")
        if next_tag:
            next_link = next_tag.get("href", "")
            if next_link and next_link.startswith("http"):
                page_url = next_link
            else:
                log("Link halaman berikutnya tidak valid.")
                break
        else:
            log("Tidak ada halaman berikutnya.")
            break

    log(f"Selesai. {len(new_articles)} berita baru ditemukan.")
    return new_articles


# =============================
# MAIN
# =============================
def main():

    print("MEMULAI SCRAPING KOMPAS TAG TEGAL")

    results = scrape_tag(BASE_URL, N)

    df = pd.DataFrame(results)

    df.to_excel("kompas_tegal.xlsx", index=False)

    print("\nSCRAPING SELESAI")
    print("Total berita:", len(results))
    print("File tersimpan: kompas_tegal.xlsx")


if __name__ == "__main__":
    main()