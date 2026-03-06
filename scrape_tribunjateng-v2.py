import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import pandas as pd
import time
import random

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    "Referer": "https://www.google.com/"
}
session = requests.Session()
session.headers.update(headers)


def get_page(url):
    try:
        res = session.get(url, timeout=10)
        if res.status_code == 200:
            return res.text
    except:
        pass
    return None


# =========================
# SCRAPE ARTIKEL
# =========================
def scrape_tribun(url):

    original_url = url

    judul = None
    penulis = None
    waktu = None
    tags = []
    isi_all = []

    # kumpulkan semua halaman artikel
    pages = [url]

    html = get_page(url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")

    # ambil pagination
    pag = soup.select(".pagination-wrap a")

    for a in pag:
        link = a.get("href")
        if link:
            full = urljoin(url, link)
            if full not in pages:
                pages.append(full)

    # loop semua halaman artikel
    for page in pages:

        html = get_page(page)
        if not html:
            continue

        soup = BeautifulSoup(html, "html.parser")

        if judul is None:
            tag = soup.select_one("h1")
            if tag:
                judul = tag.get_text(strip=True)

        if penulis is None:
            tag = soup.select_one("#penulis a")
            if tag:
                penulis = tag.get_text(strip=True)

        if waktu is None:
            tag = soup.select_one("time")
            if tag:
                waktu = tag.get_text(strip=True)

        if not tags:
            for t in soup.select(".tagcloud3"):
                tags.append(t.get_text(strip=True))

        for p in soup.select(".txt-article p"):
            isi_all.append(p.get_text(strip=True))

        time.sleep(random.uniform(2,4))

    return {
        "judul": judul,
        "penulis": penulis,
        "waktu": waktu,
        "isi": " ".join(isi_all),
        "tags": ", ".join(tags),
        "url": original_url
    }


# =========================
# SCRAPE INDEX BERITA
# =========================
def scrape_index(start_url, target_n):

    results = []
    page_url = start_url

    while len(results) < target_n:

        print("📄 membuka halaman:", page_url)

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

            print("📰 scrape:", judul)

            artikel = scrape_tribun(link)

            results.append(artikel)

            print("✅ total:", len(results))

            if len(results) >= target_n:
                break

            time.sleep(random.uniform(3,6))

        # cari pagination next
        next_tag = soup.select_one("a[rel='next']")

        if next_tag:
            page_url = next_tag["href"]
        else:
            break

    return results


# =========================
# MAIN
# =========================
start_url = "https://jateng.tribunnews.com/topic/berita-kabupaten-tegal"

target = 2

data = scrape_index(start_url, target)

df = pd.DataFrame(data)

df.to_excel("tribun_tegals.xlsx", index=False)

print("\n🎉 scraping selesai")
print("📁 file tersimpan: tribun_tegal_berkah.xlsx")